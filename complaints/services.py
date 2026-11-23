"""
Complaint operations. Every state change goes through this module, runs in a transaction,
checks the actor's permission and records an immutable ComplaintEvent.

Errors:
- django.core.exceptions.PermissionDenied: the actor may not do this.
- django.core.exceptions.ValidationError: the input or the complaint's state does not allow it.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import StudentProfile, User
from dsa.edit_distance import find_similar

from .models import Complaint, ComplaintCategory, ComplaintEvent, ComplaintSubcategory
from .notifications import notify_student
from .permissions import advisor_has_cohort, can_manage_complaint, is_complaint_owner

Status = Complaint.Status
Kind = ComplaintEvent.Kind

# Status changes a Batch Advisor or Super Admin may make (DEC-221). Resolved and Rejected
# are closing states: only the student's "Still not resolved" reopens a resolved complaint
# (DEC-222). There are no priority or overdue states (DEC-226).
STAFF_TRANSITIONS = {
    Status.RECEIVED: {Status.UNDER_REVIEW, Status.RESOLVED, Status.REJECTED},
    Status.UNDER_REVIEW: {Status.RESOLVED, Status.REJECTED},
    Status.RESOLVED: set(),
    Status.REJECTED: set(),
}
NOTE_REQUIRED = {
    Status.RESOLVED: "A resolution note is required.",
    Status.REJECTED: "A rejection reason is required.",
}
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)


def _text(value):
    return (value or "").strip()


def _locked(complaint):
    """Re-read the complaint under a row lock so concurrent actions apply one at a time."""
    return Complaint.objects.select_for_update().get(pk=complaint.pk)


def _record(complaint, actor, kind, **fields):
    event = ComplaintEvent(complaint=complaint, actor=actor, kind=kind, **fields)
    event.full_clean(exclude=["complaint", "actor", "responsible"])
    event.save()
    return event


def _touch(complaint, *fields):
    complaint.save(update_fields=[*fields, "updated_at"])


@transaction.atomic
def submit_complaint(student, *, category, title, description, subcategory=None):
    """
    Submit a complaint for the signed-in student (DEC-030, DEC-031).

    The cohort is taken from the student's own registered profile, never from the request,
    and must be active. The category (and subcategory, if given) must be active. Duplicates
    are allowed (DEC-225).
    """
    if not (student.is_authenticated and student.is_active and student.is_student):
        raise PermissionDenied("Only active students can submit complaints.")
    try:
        profile = StudentProfile.objects.select_related("batch", "semester", "section").get(user=student)
    except StudentProfile.DoesNotExist:
        raise PermissionDenied("Complete your registration before submitting a complaint.") from None
    if not all(entry.is_active for entry in (profile.batch, profile.semester, profile.section)):
        raise ValidationError("Your batch, semester or section is no longer active. Please contact the Super Admin.")

    errors = {}
    if not isinstance(category, ComplaintCategory) or not ComplaintCategory.objects.active().filter(pk=category.pk).exists():
        errors["category"] = "Choose an available category."
    if subcategory is not None and (
        not isinstance(subcategory, ComplaintSubcategory)
        or subcategory.category_id != getattr(category, "pk", None)
        or not ComplaintSubcategory.objects.active().filter(pk=subcategory.pk).exists()
    ):
        errors["subcategory"] = "Choose an available subcategory of this category."
    if errors:
        raise ValidationError(errors)

    complaint = Complaint(
        student=student,
        batch=profile.batch,
        semester=profile.semester,
        section=profile.section,
        category=category,
        subcategory=subcategory,
        title=_text(title),
        description=_text(description),
    )
    complaint.full_clean(exclude=["reference"])
    complaint.save()
    complaint.reference = f"CMP-{timezone.localdate().year}-{complaint.pk:05d}"
    complaint.save(update_fields=["reference"])
    _record(complaint, student, Kind.SUBMITTED)
    return complaint


@transaction.atomic
def change_status(actor, complaint, new_status, note="", *, expected_status=None):
    """A Batch Advisor of the exact cohort, or a Super Admin, changes the status (DEC-221).

    Resolving needs a resolution note and rejecting needs a reason; both are visible to the
    student in the history.

    `expected_status` is the status the actor saw. If given and the complaint has changed
    since (for example, another advisor of the same cohort acted first), the change is
    refused. The comparison runs under the row lock, so it is atomic. Omitted: no check.
    """
    if not can_manage_complaint(actor, complaint):
        raise PermissionDenied("You cannot change the status of this complaint.")
    complaint = _locked(complaint)
    if expected_status is not None and complaint.status != expected_status:
        raise ValidationError(
            f"This complaint is now {complaint.get_status_display()}: it changed after you opened it. "
            "Check the latest history before updating the status.",
            code="stale_status",
        )
    note = _text(note)
    if new_status not in STAFF_TRANSITIONS.get(complaint.status, set()):
        raise ValidationError(
            f"A complaint that is {complaint.get_status_display()} cannot be changed to "
            f"{Status(new_status).label if new_status in Status.values else new_status}."
        )
    if new_status in NOTE_REQUIRED and not note:
        raise ValidationError({"note": NOTE_REQUIRED[new_status]})
    old_status = complaint.status
    complaint.status = new_status
    _touch(complaint, "status")
    event = _record(complaint, actor, Kind.STATUS_CHANGED, from_status=old_status, to_status=new_status, message=note)
    # Same transaction: the student's notification commits or rolls back with the event (DEC-270).
    notify_student(event)
    return complaint


@transaction.atomic
def respond(actor, complaint, message):
    """A response from a Batch Advisor of the cohort or a Super Admin. Never changes the status (DEC-305)."""
    if not can_manage_complaint(actor, complaint):
        raise PermissionDenied("You cannot respond to this complaint.")
    complaint = _locked(complaint)
    message = _text(message)
    if not message:
        raise ValidationError({"message": "Write a response."})
    _touch(complaint)
    event = _record(complaint, actor, Kind.RESPONSE, message=message)
    # Same transaction: the student's notification commits or rolls back with the event (DEC-270).
    notify_student(event)
    return event


@transaction.atomic
def mark_still_not_resolved(student, complaint, message=""):
    """The student says a resolved complaint is still not resolved: it returns to Under Review (DEC-222)."""
    if not is_complaint_owner(student, complaint):
        raise PermissionDenied("Only the student who submitted this complaint can do this.")
    complaint = _locked(complaint)
    if complaint.status != Status.RESOLVED:
        raise ValidationError("Only a resolved complaint can be marked as still not resolved.")
    complaint.status = Status.UNDER_REVIEW
    _touch(complaint, "status")
    _record(
        complaint, student, Kind.STILL_NOT_RESOLVED,
        from_status=Status.RESOLVED, to_status=Status.UNDER_REVIEW, message=_text(message),
    )
    return complaint


@transaction.atomic
def add_further_information(student, complaint, message):
    """Add information without changing the original description or history (DEC-223)."""
    if not is_complaint_owner(student, complaint):
        raise PermissionDenied("Only the student who submitted this complaint can add information.")
    complaint = _locked(complaint)
    message = _text(message)
    if not message:
        raise ValidationError({"message": "Write the information you want to add."})
    _touch(complaint)
    return _record(complaint, student, Kind.FURTHER_INFORMATION, message=message)


@transaction.atomic
def request_cancellation(student, complaint, reason=""):
    """
    Record that the student asked to cancel the complaint (DEC-224).

    Only the request is recorded. Who acts on it, and what happens to the complaint, is
    OPEN (O28): the status does not change and nothing is deleted.
    """
    if not is_complaint_owner(student, complaint):
        raise PermissionDenied("Only the student who submitted this complaint can ask to cancel it.")
    complaint = _locked(complaint)
    _touch(complaint)
    return _record(complaint, student, Kind.CANCELLATION_REQUESTED, message=_text(reason))


def is_eligible_owner(user, complaint):
    """DEC-310: an active Batch Advisor assigned to the complaint's exact batch + semester +
    section, or an active Super Admin. The one rule used by assign_responsible and the forms."""
    return user is not None and user.is_active and (
        user.is_super_admin or (user.is_batch_advisor and advisor_has_cohort(user, complaint))
    )


def eligible_advisors(complaint):
    """Active Batch Advisors assigned to the complaint's exact cohort, by name."""
    return (
        User.objects.filter(
            role=User.Role.BATCH_ADVISOR,
            is_active=True,
            advisor_assignments__batch_id=complaint.batch_id,
            advisor_assignments__semester_id=complaint.semester_id,
            advisor_assignments__section_id=complaint.section_id,
        )
        .distinct()
        .order_by("full_name", "email")
    )


@transaction.atomic
def assign_responsible(actor, complaint, owner):
    """
    A Super Admin assigns or reassigns the responsible owner, or takes the complaint over
    (DEC-227, DEC-228, DEC-310). The owner must satisfy is_eligible_owner. Nothing assigns
    an owner automatically, and the owner grants no extra access: every advisor of the exact
    cohort keeps their visibility and actions. Repeating the current owner is a no-op.
    """
    if not (actor.is_authenticated and actor.is_active and actor.is_super_admin):
        raise PermissionDenied("Only the Super Admin can assign the responsible owner.")
    complaint = _locked(complaint)
    if not is_eligible_owner(owner, complaint):
        raise ValidationError(
            {"responsible": "Choose an active Batch Advisor assigned to this exact cohort, or a Super Admin."}
        )
    if complaint.responsible_id == owner.pk:
        return complaint
    complaint.responsible = owner
    _touch(complaint, "responsible")
    _record(complaint, actor, Kind.RESPONSIBLE_CHANGED, responsible=owner)
    return complaint


def possible_duplicates(student, title):
    """
    The student's own open complaints whose titles are similar to `title` (edit distance,
    dsa.edit_distance), most similar first, for a "you may have already raised this" warning
    before submitting (DEC-225). It never blocks a submission, and it never looks at other
    students' complaints.
    """
    own_open = Complaint.objects.filter(student=student, status__in=OPEN_STATUSES).order_by("-created_at", "-id")
    return find_similar(title, list(own_open), key=lambda complaint: complaint.title)
