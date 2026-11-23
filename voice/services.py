"""
Student Voice operations. Every change goes through this module.

Errors:
- django.core.exceptions.PermissionDenied: the person may not do this.
- django.core.exceptions.ValidationError: the input or the submission's state does not allow it.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import StudentProfile

from .models import TEXT_MAX, Submission
from .notifications import notify_student
from .permissions import can_act


def _locked(submission):
    """Re-read under a row lock, so two advisors acting together are handled one at a time."""
    return Submission.objects.select_for_update().get(pk=submission.pk)


@transaction.atomic
def submit(student, *, type, text):
    """A student sends an Idea, Question or Feedback. The cohort comes from their own profile."""
    if not (student.is_authenticated and student.is_active and student.is_student):
        raise PermissionDenied("Only active students can use Student Voice.")
    try:
        profile = StudentProfile.objects.select_related("batch", "semester", "section").get(user=student)
    except StudentProfile.DoesNotExist:
        raise PermissionDenied("Complete your registration first.") from None
    if not all(entry.is_active for entry in (profile.batch, profile.semester, profile.section)):
        raise ValidationError("Your batch, semester or section is no longer active. Please contact the Super Admin.")

    submission = Submission(
        student=student, batch=profile.batch, semester=profile.semester, section=profile.section,
        type=type, text=(text or "").strip(),
    )
    submission.full_clean()
    submission.save()
    return submission


@transaction.atomic
def answer(advisor, submission, text):
    """The one official answer to a Question, or the one optional reply to an Idea or Feedback.
    A reply also marks the Idea or Feedback as reviewed. Once saved it cannot be changed."""
    if not can_act(advisor, submission):
        raise PermissionDenied("You cannot answer this submission.")
    submission = _locked(submission)
    if submission.answer:
        raise ValidationError("This submission already has a response, and it cannot be changed.")
    text = (text or "").strip()
    if not text:
        raise ValidationError({"answer": "Write your response."})
    if len(text) > TEXT_MAX:
        raise ValidationError({"answer": f"Keep your response to {TEXT_MAX} characters."})

    now = timezone.now()
    submission.answer, submission.answered_by, submission.answered_at = text, advisor, now
    fields = ["answer", "answered_by", "answered_at", "status"]
    if submission.is_question:
        submission.status = Submission.Status.ANSWERED
    else:
        submission.status = Submission.Status.REVIEWED
        if submission.reviewed_at is None:
            submission.reviewed_by, submission.reviewed_at = advisor, now
            fields += ["reviewed_by", "reviewed_at"]
    submission.save(update_fields=fields)
    notify_student(submission)
    return submission


@transaction.atomic
def mark_reviewed(advisor, submission):
    """Mark an Idea or Feedback as reviewed. A Question is closed only by its answer."""
    if not can_act(advisor, submission):
        raise PermissionDenied("You cannot review this submission.")
    submission = _locked(submission)
    if submission.is_question:
        raise ValidationError("A question is completed by answering it.")
    if submission.status != Submission.Status.WAITING:
        raise ValidationError("This submission is already reviewed.")
    submission.status = Submission.Status.REVIEWED
    submission.reviewed_by, submission.reviewed_at = advisor, timezone.now()
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return submission
