"""
Section issue operations. Every change goes through this module, in one transaction.

Errors:
- django.core.exceptions.PermissionDenied: the person may not do this.
- django.core.exceptions.ValidationError: the input or the issue's state does not allow it.

Locks follow the global order of COLLECTIVE_ISSUES_SPEC.md section 5.7: publishing and supporting
take the cohort's Section row first, then the issue row. Advisor actions take only the issue row.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.representation import Cohort, cohort_is_active, current_representative, lock_sections, post_in

from .models import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    RESPONSE_MAX,
    TITLE_MAX,
    TITLE_MIN,
    CollectiveIssue,
    IssueEvent,
    Support,
)
from .notifications import notify_published, notify_representatives
from .permissions import can_act, is_cohort_student

Status = CollectiveIssue.Status
Kind = IssueEvent.Kind

SUPPORT_CLOSED = "Support is closed for this issue."
ISSUE_FINAL = "This issue is resolved. Resolved is final."
STALE_STATUS = "This issue changed after you opened it. Check the latest status and try again."


def _locked(issue):
    """Re-read under a row lock, so actions on one issue are handled one at a time."""
    return CollectiveIssue.objects.select_for_update().get(pk=issue.pk)


def _text(value):
    return (value or "").strip()


def validate_content(title, description):
    """The trimmed title and description, or a ValidationError naming the field."""
    title, description = _text(title), _text(description)
    errors = {}
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        errors["title"] = f"Write a title of {TITLE_MIN} to {TITLE_MAX} characters."
    if not DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX:
        errors["description"] = f"Write a description of {DESCRIPTION_MIN} to {DESCRIPTION_MAX} characters."
    if errors:
        raise ValidationError(errors)
    return title, description


@transaction.atomic
def publish_issue(user, *, title, description):
    """The current CR or GR publishes an issue for their own cohort, taken from their current
    representation period and never from the request (DEC-040, DEC-324)."""
    title, description = validate_content(title, description)
    period = current_representative(user)
    if period is None:
        raise PermissionDenied("Only your section's current CR or GR can raise an issue.")
    lock_sections([period.section_id])
    # Read again under the cohort lock: the post or the cohort may have just changed.
    period = current_representative(user)
    if period is None:
        raise PermissionDenied("Only your section's current CR or GR can raise an issue.")
    cohort = Cohort.of(period)
    if not cohort_is_active(cohort):
        raise ValidationError("Your batch, semester or section is inactive, so new issues can't be raised.")

    issue = CollectiveIssue.objects.create(raised_by=user, raised_as=post_in(period, user.pk), title=title,
                                           description=description, **cohort.filter())
    issue.reference = f"CI-{timezone.localdate().year}-{issue.pk:05d}"
    issue.save(update_fields=["reference"])
    event = IssueEvent.objects.create(issue=issue, kind=Kind.RAISED, actor=user)
    notify_published(issue, event)
    return issue


@transaction.atomic
def support_issue(student, issue):
    """Record one student's support. Returns True if recorded, False if they already support it.
    The unique constraint is what makes a double submission impossible."""
    lock_sections([issue.section_id])
    issue = _locked(issue)
    if not is_cohort_student(student, issue):
        raise PermissionDenied("Only students of this section can support this issue.")
    if issue.first_response_at is not None or not cohort_is_active(Cohort.of(issue)):
        raise ValidationError(SUPPORT_CLOSED)
    if Support.objects.filter(issue=issue, student=student).exists():
        return False
    try:
        with transaction.atomic():  # a savepoint: a violation must not break the outer transaction
            Support.objects.create(issue=issue, student=student)
    except IntegrityError:
        return False
    return True


def _start_action(advisor, issue, expected_status):
    if not can_act(advisor, issue):
        raise PermissionDenied("Only a Batch Advisor of this cohort can act on this issue.")
    issue = _locked(issue)
    if issue.status == Status.RESOLVED:
        raise ValidationError(ISSUE_FINAL)
    if expected_status is not None and issue.status != expected_status:
        raise ValidationError(STALE_STATUS)
    return issue


def _message(text, field):
    text = _text(text)
    if not text:
        label = "resolution note" if field == "note" else "response"
        raise ValidationError({field: f"Write the {label}."})
    if len(text) > RESPONSE_MAX:
        raise ValidationError({field: f"Keep this to {RESPONSE_MAX} characters."})
    return text


@transaction.atomic
def mark_under_review(advisor, issue, *, expected_status=None):
    """Status only. It needs no response and does not close support."""
    issue = _start_action(advisor, issue, expected_status)
    if issue.status != Status.RECEIVED:
        raise ValidationError("This issue is already under review.")
    issue.status = Status.UNDER_REVIEW
    issue.save(update_fields=["status", "updated_at"])
    IssueEvent.objects.create(issue=issue, kind=Kind.STATUS_CHANGED, actor=advisor,
                              from_status=Status.RECEIVED, to_status=Status.UNDER_REVIEW)
    return issue


@transaction.atomic
def send_response(advisor, issue, text):
    """An official response: repeatable until resolved, never changes the status. The first one
    closes support."""
    text = _message(text, "response")
    issue = _start_action(advisor, issue, None)
    if issue.first_response_at is None:
        issue.first_response_at = timezone.now()
        issue.save(update_fields=["first_response_at", "updated_at"])
    event = IssueEvent.objects.create(issue=issue, kind=Kind.RESPONSE, actor=advisor, message=text)
    notify_representatives(issue, event)
    return issue


@transaction.atomic
def resolve(advisor, issue, note, *, expected_status=None):
    """Final. The mandatory note counts as an official response, so one action sends one
    notification and closes support if nothing has closed it yet."""
    note = _message(note, "note")
    issue = _start_action(advisor, issue, expected_status)
    now = timezone.now()
    previous = issue.status
    issue.status, issue.resolution_note, issue.resolved_at = Status.RESOLVED, note, now
    if issue.first_response_at is None:
        issue.first_response_at = now
    issue.save(update_fields=["status", "resolution_note", "resolved_at", "first_response_at", "updated_at"])
    event = IssueEvent.objects.create(issue=issue, kind=Kind.STATUS_CHANGED, actor=advisor, from_status=previous,
                                      to_status=Status.RESOLVED, message=note)
    notify_representatives(issue, event)
    return issue
