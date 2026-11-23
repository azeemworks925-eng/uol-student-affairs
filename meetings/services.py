"""
Meeting operations. Every change goes through this module.

    Requested ──> Confirmed       (advisor)
    Requested ──> Time suggested  (advisor)
    Requested ──> Declined        (advisor, reason required)
    Time suggested ──> Confirmed  (student accepts)
    Time suggested ──> Declined   (student declines)
    Confirmed ──> Cancelled       (student or advisor, reason required)

Declined and Cancelled are final. Rescheduling is a cancellation plus a new request.

Errors:
- django.core.exceptions.PermissionDenied: the person may not do this.
- django.core.exceptions.ValidationError: the input or the meeting's state does not allow it.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import AdvisorAssignment, StudentProfile

from .models import DURATIONS, LOCATION_MAX, NOTE_MAX, Meeting, MeetingEvent
from .notifications import notify_student
from .permissions import advisor_can_act, is_own_meeting

Status = Meeting.Status
Kind = MeetingEvent.Kind
PAST_MESSAGE = "Choose a date and time in the future."


def _locked(meeting):
    """Re-read under a row lock, so two people acting together are handled one at a time."""
    return Meeting.objects.select_for_update().get(pk=meeting.pk)


def _record(meeting, kind, actor, note=""):
    event = MeetingEvent.objects.create(meeting=meeting, kind=kind, actor=actor, note=note)
    notify_student(event)
    return event


def _require_status(meeting, status, message):
    if meeting.status != status:
        raise ValidationError(message)


def _clean_slot(starts_at, duration, location):
    if starts_at is None or starts_at <= timezone.now():
        raise ValidationError(PAST_MESSAGE)
    if duration not in DURATIONS:
        raise ValidationError("Choose a duration of 15, 30, 45 or 60 minutes.")
    location = (location or "").strip()
    if not location:
        raise ValidationError("Enter where the meeting will take place.")
    if len(location) > LOCATION_MAX:
        raise ValidationError(f"Keep the location to {LOCATION_MAX} characters.")
    return location


def _clean_reason(reason, required_message):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError(required_message)
    if len(reason) > NOTE_MAX:
        raise ValidationError(f"Keep this to {NOTE_MAX} characters.")
    return reason


def _active_profile(student):
    try:
        profile = StudentProfile.objects.select_related("batch", "semester", "section").get(user=student)
    except StudentProfile.DoesNotExist:
        raise PermissionDenied("Complete your registration first.") from None
    if not all(entry.is_active for entry in (profile.batch, profile.semester, profile.section)):
        raise ValidationError("This batch, semester or section is no longer active.")
    return profile


@transaction.atomic
def request_meeting(student, *, reason, preferred_at):
    """A student asks to meet. The cohort comes from their own profile."""
    if not (student.is_authenticated and student.is_active and student.is_student):
        raise PermissionDenied("Only active students can request a meeting.")
    profile = _active_profile(student)
    if not AdvisorAssignment.objects.filter(
        batch=profile.batch, semester=profile.semester, section=profile.section, advisor__is_active=True
    ).exists():
        raise ValidationError("No Batch Advisor is assigned to your section yet.")
    if preferred_at is None or preferred_at <= timezone.now():
        raise ValidationError(PAST_MESSAGE)
    meeting = Meeting(
        student=student, batch=profile.batch, semester=profile.semester, section=profile.section,
        reason=(reason or "").strip(), preferred_at=preferred_at,
    )
    meeting.full_clean()
    meeting.save()
    _record(meeting, Kind.REQUESTED, student)
    return meeting


@transaction.atomic
def schedule(advisor, student, *, reason, starts_at, duration, location):
    """An advisor books a meeting directly with a student of an assigned cohort."""
    if not (student.is_active and student.is_student):
        raise ValidationError("Choose an active student.")
    profile = _active_profile(student)
    if not (advisor.is_active and advisor.is_batch_advisor and AdvisorAssignment.objects.filter(
        advisor=advisor, batch=profile.batch, semester=profile.semester, section=profile.section,
    ).exists()):
        raise PermissionDenied("This student is not in one of your cohorts.")
    location = _clean_slot(starts_at, duration, location)
    meeting = Meeting(
        student=student, batch=profile.batch, semester=profile.semester, section=profile.section,
        advisor=advisor, reason=(reason or "").strip(), status=Status.CONFIRMED,
        starts_at=starts_at, duration_minutes=duration, location=location,
    )
    meeting.full_clean()
    meeting.save()
    _record(meeting, Kind.SCHEDULED, advisor)
    return meeting


def _set_slot(meeting, advisor, status, starts_at, duration, location, note=""):
    meeting.advisor, meeting.status = advisor, status
    meeting.starts_at, meeting.duration_minutes, meeting.location = starts_at, duration, location
    meeting.suggestion_note = note
    meeting.save(update_fields=["advisor", "status", "starts_at", "duration_minutes", "location", "suggestion_note"])


@transaction.atomic
def confirm(advisor, meeting, *, starts_at, duration, location):
    """Confirm a request. The advisor who confirms becomes the meeting's advisor."""
    if not advisor_can_act(advisor, meeting):
        raise PermissionDenied("You cannot confirm this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.REQUESTED, "This request has already been handled.")
    location = _clean_slot(starts_at, duration, location)
    _set_slot(meeting, advisor, Status.CONFIRMED, starts_at, duration, location)
    _record(meeting, Kind.CONFIRMED, advisor)
    return meeting


@transaction.atomic
def suggest(advisor, meeting, *, starts_at, duration, location, note=""):
    """Offer another time. The student then accepts or declines it."""
    if not advisor_can_act(advisor, meeting):
        raise PermissionDenied("You cannot suggest a time for this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.REQUESTED, "This request has already been handled.")
    location = _clean_slot(starts_at, duration, location)
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise ValidationError(f"Keep the note to {NOTE_MAX} characters.")
    _set_slot(meeting, advisor, Status.TIME_SUGGESTED, starts_at, duration, location, note)
    _record(meeting, Kind.SUGGESTED, advisor, note)
    return meeting


@transaction.atomic
def decline(advisor, meeting, reason):
    """An advisor declines a request, with a reason the student can read."""
    if not advisor_can_act(advisor, meeting):
        raise PermissionDenied("You cannot decline this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.REQUESTED, "This request has already been handled.")
    reason = _clean_reason(reason, "Give a reason for declining.")
    meeting.advisor, meeting.status, meeting.closed_reason = advisor, Status.DECLINED, reason
    meeting.save(update_fields=["advisor", "status", "closed_reason"])
    _record(meeting, Kind.DECLINED, advisor, reason)
    return meeting


@transaction.atomic
def accept_suggestion(student, meeting):
    """The student accepts the suggested time, while it is still in the future."""
    if not is_own_meeting(student, meeting):
        raise PermissionDenied("You cannot accept this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.TIME_SUGGESTED, "There is no suggested time to accept.")
    if meeting.starts_at <= timezone.now():
        raise ValidationError("This suggested time has passed. Decline it and send a new request.")
    meeting.status = Status.CONFIRMED
    meeting.save(update_fields=["status"])
    _record(meeting, Kind.ACCEPTED, student)
    return meeting


@transaction.atomic
def decline_suggestion(student, meeting):
    """The student declines the suggested time. The meeting is closed."""
    if not is_own_meeting(student, meeting):
        raise PermissionDenied("You cannot decline this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.TIME_SUGGESTED, "There is no suggested time to decline.")
    meeting.status = Status.DECLINED
    meeting.save(update_fields=["status"])
    _record(meeting, Kind.DECLINED, student)
    return meeting


@transaction.atomic
def cancel(user, meeting, reason):
    """The student or an advisor of the cohort cancels a confirmed meeting before it starts."""
    if not (is_own_meeting(user, meeting) or advisor_can_act(user, meeting)):
        raise PermissionDenied("You cannot cancel this meeting.")
    meeting = _locked(meeting)
    _require_status(meeting, Status.CONFIRMED, "Only a confirmed meeting can be cancelled.")
    if meeting.starts_at <= timezone.now():
        raise ValidationError("This meeting has already started, so it can no longer be cancelled.")
    reason = _clean_reason(reason, "Give a reason for cancelling.")
    meeting.status, meeting.closed_reason = Status.CANCELLED, reason
    meeting.save(update_fields=["status", "closed_reason"])
    _record(meeting, Kind.CANCELLED, user, reason)
    return meeting
