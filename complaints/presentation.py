"""
How complaints read to the people who use them (Complaints Parts 2 and 3).

Only recorded events are shown, with plain-language labels. Students see their history
oldest first, with staff by role only, never by name or account. Batch Advisors see it newest
first, with names and roles (P3-7). Changes of responsible owner are not shown to either
while O27 is open.
"""

from dataclasses import dataclass

from django.urls import reverse

from dsa.sorting import merge_sort
from notifications.models import Notification

from .models import Complaint, ComplaintEvent

Status = Complaint.Status
Kind = ComplaintEvent.Kind

# The existing status pill tones in static/css/app.css (DEC-301).
STATUS_TONES = {
    Status.RECEIVED: "received",
    Status.UNDER_REVIEW: "review",
    Status.RESOLVED: "resolved",
    Status.REJECTED: "rejected",
}

# Owner changes are internal to staff (DEC-310): never shown to students. The Batch Advisor
# workspace keeps its Part 3 history; the Super Admin workspace shows them (Part 4 Stage 1).
STUDENT_HIDDEN_KINDS = {Kind.RESPONSIBLE_CHANGED}

MESSAGE_LABELS = {
    Status.RESOLVED: "Resolution note",
    Status.REJECTED: "Reason for rejection",
}


def status_tone(status):
    return STATUS_TONES.get(status, "received")


@dataclass(frozen=True)
class TimelineEntry:
    title: str
    when: object
    by: str = ""
    message: str = ""
    message_label: str = ""
    status: str = ""  # the status the complaint moved to, if any
    note: str = ""
    by_student: bool = False

    @property
    def status_label(self):
        return Status(self.status).label if self.status else ""

    @property
    def tone(self):
        return status_tone(self.status) if self.status else ""


def _staff_role(actor):
    return actor.get_role_display()


def _staff_name(actor):
    return f"{actor.get_full_name()} ({actor.get_role_display()})"


def _entry(event, audience):
    """One history entry. Students see staff by role and "you"; staff see names (Part 3)."""
    kind, student = event.kind, audience == "student"
    student_name = "" if student else event.complaint.student.get_full_name()
    if kind == Kind.SUBMITTED:
        title = "You submitted this complaint" if student else f"{student_name} submitted this complaint"
        return TimelineEntry(title, event.created_at, by_student=True, status=Status.RECEIVED)
    if kind == Kind.STATUS_CHANGED:
        new = Status(event.to_status)
        return TimelineEntry(
            f"Status changed to {new.label}", event.created_at,
            by=_staff_role(event.actor) if student else _staff_name(event.actor),
            message=event.message, message_label=MESSAGE_LABELS.get(new, "Note"), status=new,
        )
    if kind == Kind.STILL_NOT_RESOLVED:
        return TimelineEntry(
            "You said this is still not resolved" if student else f"{student_name} marked this as still not resolved",
            event.created_at, message=event.message,
            message_label="Your note" if student else "Student's note",
            status=Status.UNDER_REVIEW, by_student=True, note="The complaint returned to Under Review.",
        )
    if kind == Kind.RESPONSE:
        return TimelineEntry(
            f"Response from {_staff_role(event.actor) if student else _staff_name(event.actor)}",
            event.created_at, message=event.message,
        )
    if kind == Kind.FURTHER_INFORMATION:
        return TimelineEntry(
            "You added further information" if student else f"Further information from {student_name}",
            event.created_at, message=event.message, by_student=True,
        )
    if kind == Kind.RESPONSIBLE_CHANGED and not student:
        owner = event.responsible
        title = (
            f"{_staff_name(event.actor)} took over this complaint" if owner.pk == event.actor_id
            else f"Responsible owner set to {_staff_name(owner)}"
        )
        return TimelineEntry(title, event.created_at, by="" if owner.pk == event.actor_id else _staff_name(event.actor))
    if kind == Kind.CANCELLATION_REQUESTED:
        return TimelineEntry(
            "You asked to cancel this complaint" if student else f"{student_name} asked to cancel this complaint",
            event.created_at, message=event.message,
            message_label="Your reason" if student else "Student's reason", by_student=True,
            note="Your request was recorded. It does not cancel or change the complaint by itself." if student
            else "Recorded only. The status does not change.",
        )
    return None


def _timeline(complaint, audience, newest_first, include_owner_changes=False):
    order = ("-created_at", "-id") if newest_first else ("created_at", "id")
    events = complaint.events.select_related("actor", "responsible", "complaint__student").order_by(*order)
    if not include_owner_changes:
        events = events.exclude(kind__in=STUDENT_HIDDEN_KINDS)
    return [entry for entry in (_entry(event, audience) for event in events) if entry]


def student_timeline(complaint):
    """The complaint's history as the student sees it, oldest first."""
    return _timeline(complaint, "student", newest_first=False)


def staff_timeline(complaint, include_owner_changes=False):
    """Staff history, newest first (P3-7), with names and roles. Owner changes are included
    for the Super Admin workspace; the Batch Advisor workspace keeps its Part 3 history."""
    return _timeline(complaint, "staff", newest_first=True, include_owner_changes=include_owner_changes)


def has_cancellation_request(complaint):
    return complaint.events.filter(kind=Kind.CANCELLATION_REQUESTED).exists()


JOURNEY = (Status.RECEIVED, Status.UNDER_REVIEW)


def status_journey(complaint):
    """Received → Under Review → Resolved or Rejected, marking where the complaint is now."""
    final = complaint.status if complaint.status in (Status.RESOLVED, Status.REJECTED) else Status.RESOLVED
    steps = [*JOURNEY, final]
    current = steps.index(complaint.status) if complaint.status in steps else 0
    closing_pending = complaint.status not in (Status.RESOLVED, Status.REJECTED)
    return [
        {
            "label": "Resolved or Rejected" if (step == final and closing_pending) else Status(step).label,
            "state": "done" if index < current else ("current" if index == current else "upcoming"),
            "tone": status_tone(step),
        }
        for index, step in enumerate(steps)
    ]


# --- Student Home: "Your latest updates" ---------------------------------------------------------

STUDENT_UPDATE_KINDS = (Kind.STATUS_CHANGED, Kind.RESPONSE)  # the two events that notify (DEC-270)
HOME_UPDATE_LIMIT = 5


@dataclass(frozen=True)
class StudentUpdate:
    reference: str
    complaint_title: str
    headline: str  # the full sentence, used by the personal summary
    label: str  # the row title next to the reference
    status: str
    status_label: str
    tone: str
    when: object
    url: str
    is_new: bool  # its notification is still unread


def student_updates(student, limit=HOME_UPDATE_LIMIT):
    """The student's latest staff updates on their own complaints: status changes and responses,
    newest first (merge sort, dsa.sorting). An update is "new" while its notification is unread."""
    events = list(
        ComplaintEvent.objects.filter(complaint__student=student, kind__in=STUDENT_UPDATE_KINDS)
        .exclude(actor=student).select_related("complaint").order_by()
    )
    latest = merge_sort(events, key=lambda e: (e.created_at, e.pk), reverse=True)[:limit]
    unread = set(
        Notification.objects.filter(
            recipient=student, source_type=ComplaintEvent._meta.label_lower,
            source_id__in=[event.pk for event in latest], read_at__isnull=True,
        ).values_list("source_id", flat=True)
    )
    updates = []
    for event in latest:
        complaint = event.complaint
        if event.kind == Kind.STATUS_CHANGED:
            status, headline = event.to_status, f"{complaint.reference} is now {event.get_to_status_display()}."
            label = f"Status changed to {event.get_to_status_display()}"
        else:
            status, headline = complaint.status, f"New response on {complaint.reference}."
            label = "New response from staff"
        updates.append(StudentUpdate(
            reference=complaint.reference, complaint_title=complaint.title, headline=headline, label=label,
            status=status, status_label=Status(status).label, tone=status_tone(status), when=event.created_at,
            url=reverse("student_complaint_detail", args=[complaint.reference]), is_new=event.pk in unread,
        ))
    return updates
