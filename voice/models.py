"""
Student Voice (DEC-050 to DEC-052, DEC-250 to DEC-254, DEC-326).

One table, one row per submission: an Idea, a Question or Feedback, as typed text. There is no
tracking ID, chat, follow-up or attachment. The row also holds the single answer or reply, so
"one answer at most" is simply one column that can be written once.

The cohort (batch + semester + section) is copied from the student's profile at submission and
never changes, so the submission stays with the advisors of that exact cohort (DEC-205).

Changes go through voice.services. Records cannot be deleted, and the ORM refuses bulk changes.
Raw SQL is outside what Django can protect.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models
from django.db.models import Q

TEXT_MIN = 10
TEXT_MAX = 2000
LENGTH_MESSAGE = f"Write between {TEXT_MIN} and {TEXT_MAX} characters."

# These never change after submission.
FROZEN_FIELDS = ("student_id", "batch_id", "semester_id", "section_id", "type", "text")
# These never change once an answer or reply exists.
ANSWER_FIELDS = ("answer", "answered_by_id", "answered_at")


class ProtectedSubmissionError(ValidationError):
    """An attempt to change or delete a submission outside voice.services."""


class SubmissionQuerySet(models.QuerySet):
    """Refuses the bulk operations that would skip Submission.save() and delete()."""

    def update(self, **kwargs):
        raise ProtectedSubmissionError("Submissions cannot be bulk-updated. Use voice.services.")

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        raise ProtectedSubmissionError("Submissions cannot be bulk-updated. Use voice.services.")

    bulk_update.alters_data = True

    def delete(self):
        raise ProtectedSubmissionError("Submissions cannot be deleted.")

    delete.alters_data = True
    delete.queryset_only = True

    def bulk_create(self, objs, *args, update_conflicts=False, **kwargs):
        if update_conflicts:
            raise ProtectedSubmissionError("Submissions cannot be overwritten by bulk_create.")
        return super().bulk_create(objs, *args, **kwargs)

    bulk_create.alters_data = True


class Submission(models.Model):
    class Type(models.TextChoices):
        IDEA = "idea", "Idea"
        QUESTION = "question", "Question"
        FEEDBACK = "feedback", "Feedback"

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        REVIEWED = "reviewed", "Reviewed"  # Ideas and Feedback
        ANSWERED = "answered", "Answered"  # Questions

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="voice_submissions",
        limit_choices_to={"role": "student"},
    )
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="voice_submissions")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="voice_submissions")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="voice_submissions")
    type = models.CharField(max_length=10, choices=Type.choices)
    text = models.TextField(
        max_length=TEXT_MAX,
        validators=[MinLengthValidator(TEXT_MIN, LENGTH_MESSAGE), MaxLengthValidator(TEXT_MAX, LENGTH_MESSAGE)],
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    # The one official answer (Question) or optional reply (Idea, Feedback).
    answer = models.TextField(max_length=TEXT_MAX, blank=True, validators=[MaxLengthValidator(TEXT_MAX)])
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Student Voice submission"
        indexes = [
            models.Index(fields=["batch", "semester", "section", "status"], name="voice_cohort_status_idx"),
            models.Index(fields=["student", "-created_at"], name="voice_student_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(type__in=["idea", "question", "feedback"]), name="voice_type_valid"),
            # An answer, its author and its time exist together or not at all.
            models.CheckConstraint(
                condition=Q(answer="", answered_by__isnull=True, answered_at__isnull=True)
                | (~Q(answer="") & Q(answered_by__isnull=False, answered_at__isnull=False)),
                name="voice_answer_fields",
            ),
            models.CheckConstraint(
                condition=Q(reviewed_by__isnull=True, reviewed_at__isnull=True)
                | Q(reviewed_by__isnull=False, reviewed_at__isnull=False),
                name="voice_review_fields",
            ),
            # Waiting: nothing done yet. Reviewed: never a Question. Answered: only a Question.
            models.CheckConstraint(
                condition=Q(status="waiting", answer="", reviewed_at__isnull=True)
                | (Q(status="reviewed", reviewed_at__isnull=False) & ~Q(type="question"))
                | (Q(status="answered", type="question") & ~Q(answer="")),
                name="voice_status_matches_record",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} #{self.pk}"

    @property
    def is_question(self):
        return self.type == self.Type.QUESTION

    @property
    def answer_label(self):
        return "Official answer" if self.is_question else "Reply from your Batch Advisor"

    def save(self, *args, **kwargs):
        # Compare with the stored row, not in-memory state, so a rebuilt object cannot overwrite it.
        if self.pk is not None and not kwargs.get("force_insert"):
            stored = Submission._base_manager.filter(pk=self.pk).values(*FROZEN_FIELDS, *ANSWER_FIELDS).first()
            if stored:
                if any(stored[field] != getattr(self, field) for field in FROZEN_FIELDS):
                    raise ProtectedSubmissionError("A submission cannot be changed after it is sent.")
                if stored["answer"] and any(stored[field] != getattr(self, field) for field in ANSWER_FIELDS):
                    raise ProtectedSubmissionError("An answer or reply cannot be changed once it is sent.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedSubmissionError("Submissions cannot be deleted.")
