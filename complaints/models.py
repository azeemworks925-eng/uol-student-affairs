"""
Complaints (DEC-030, DEC-031, DEC-220 to DEC-230).

A complaint belongs to the student who submitted it and records the exact cohort
(batch + semester + section, DEC-205) the student was in at submission. Every change is an
immutable ComplaintEvent, so the original description and the full history are never lost
(DEC-223). Records are never deleted: foreign keys use PROTECT, and academic structure and
categories are deactivated rather than deleted (DEC-210).

State changes go through complaints.services; access is decided by complaints.permissions.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models import Q

from academics.models import ActiveQuerySet

# TextField max_length is not checked by full_clean(), so the limit is also a validator.
TEXT_LIMIT = 5000


class ComplaintCategory(models.Model):
    """A main complaint category, managed by the Super Admin (DEC-220)."""

    name = models.CharField(max_length=80, unique=True)
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers are listed first.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "complaint categories"

    def __str__(self):
        return self.name


class ComplaintSubcategory(models.Model):
    """An optional subcategory within a main category (DEC-220)."""

    category = models.ForeignKey(ComplaintCategory, on_delete=models.PROTECT, related_name="subcategories")
    name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers are listed first.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["category__position", "category__name", "position", "name"]
        verbose_name_plural = "complaint subcategories"
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_name_per_category")
        ]

    def __str__(self):
        return f"{self.category} / {self.name}"


class ComplaintStatus(models.TextChoices):
    # DEC-221. There are no priority levels or overdue states (DEC-226).
    RECEIVED = "received", "Received"
    UNDER_REVIEW = "under_review", "Under Review"
    RESOLVED = "resolved", "Resolved"
    REJECTED = "rejected", "Rejected"


class ComplaintEventKind(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    STATUS_CHANGED = "status_changed", "Status changed"
    STILL_NOT_RESOLVED = "still_not_resolved", "Marked still not resolved"  # DEC-222
    RESPONSE = "response", "Response"
    FURTHER_INFORMATION = "further_information", "Further information"  # DEC-223
    # Recorded only. How a request is acted on is OPEN (O28); it does not change the status.
    CANCELLATION_REQUESTED = "cancellation_requested", "Cancellation requested"  # DEC-224
    RESPONSIBLE_CHANGED = "responsible_changed", "Responsible owner changed"  # DEC-227, DEC-228


STATUS_KINDS = [ComplaintEventKind.STATUS_CHANGED, ComplaintEventKind.STILL_NOT_RESOLVED]
TEXT_REQUIRED_KINDS = [ComplaintEventKind.RESPONSE, ComplaintEventKind.FURTHER_INFORMATION]
CLOSING_STATUSES = [ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED]


class Complaint(models.Model):
    Status = ComplaintStatus

    # Human-readable and unique (DEC-031), e.g. CMP-2026-00042. Derived from the primary key
    # inside the submission transaction, so concurrent submissions cannot collide. It is empty
    # only for the instant between the insert and that update.
    reference = models.CharField(max_length=20, unique=True, null=True, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="complaints",
        limit_choices_to={"role": "student"},
    )
    # The cohort at submission (DEC-205). Kept even if the student's profile later changes,
    # and even if an entry is deactivated (DEC-210).
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="complaints")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="complaints")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="complaints")
    category = models.ForeignKey(ComplaintCategory, on_delete=models.PROTECT, related_name="complaints")
    subcategory = models.ForeignKey(
        ComplaintSubcategory, on_delete=models.PROTECT, null=True, blank=True, related_name="complaints"
    )
    title = models.CharField(max_length=150)
    # The original description. Never edited: further information is added as events (DEC-223).
    description = models.TextField(max_length=TEXT_LIMIT, validators=[MaxLengthValidator(TEXT_LIMIT)])
    status = models.CharField(max_length=20, choices=ComplaintStatus.choices, default=ComplaintStatus.RECEIVED)
    # The responsible owner (DEC-227). How it is designated by default is OPEN (O27), so it
    # starts empty and is set only explicitly by the Super Admin (reassign / take over, DEC-228).
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="responsible_complaints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Advisor and Super Admin lists: by exact cohort, then status.
            models.Index(fields=["batch", "semester", "section", "status"], name="complaint_cohort_status_idx"),
            models.Index(fields=["student", "-created_at"], name="complaint_student_recent_idx"),
            models.Index(fields=["status", "-created_at"], name="complaint_status_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ComplaintStatus.values), name="complaint_status_valid"
            ),
        ]

    def __str__(self):
        return self.reference or f"Complaint #{self.pk}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._stored_description = instance.__dict__.get("description")
        return instance

    def clean(self):
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "This subcategory does not belong to the chosen category."})

    def save(self, *args, **kwargs):
        stored = getattr(self, "_stored_description", None)
        if self.pk and stored is not None and self.description != stored:
            raise ValidationError("A complaint's original description cannot be changed (DEC-223).")
        super().save(*args, **kwargs)
        self._stored_description = self.description

    def delete(self, *args, **kwargs):
        raise ValidationError("Complaints cannot be deleted (DEC-224).")

    @property
    def cohort(self):
        return self.batch, self.semester, self.section


class ComplaintEvent(models.Model):
    """One immutable entry in a complaint's history."""

    Kind = ComplaintEventKind

    complaint = models.ForeignKey(Complaint, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=30, choices=ComplaintEventKind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=20, choices=ComplaintStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=ComplaintStatus.choices, blank=True)
    # The rejection reason, resolution note, response or further information.
    message = models.TextField(max_length=TEXT_LIMIT, blank=True, validators=[MaxLengthValidator(TEXT_LIMIT)])
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["complaint", "created_at"], name="complaint_event_timeline_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=ComplaintEventKind.values), name="complaint_event_kind_valid"
            ),
            # Status events record both ends of the change; other events record neither.
            models.CheckConstraint(
                condition=(
                    Q(kind__in=STATUS_KINDS) & ~Q(from_status="") & ~Q(to_status="")
                    | ~Q(kind__in=STATUS_KINDS) & Q(from_status="") & Q(to_status="")
                ),
                name="complaint_event_status_fields",
            ),
            # DEC-221: a rejection reason and a resolution note are mandatory.
            models.CheckConstraint(
                condition=~(
                    Q(kind=ComplaintEventKind.STATUS_CHANGED, to_status__in=CLOSING_STATUSES)
                    & Q(message="")
                ),
                name="complaint_event_closing_note_required",
            ),
            models.CheckConstraint(
                condition=~(Q(kind__in=TEXT_REQUIRED_KINDS) & Q(message="")),
                name="complaint_event_text_required",
            ),
            models.CheckConstraint(
                condition=Q(kind=ComplaintEventKind.RESPONSIBLE_CHANGED, responsible__isnull=False)
                | ~Q(kind=ComplaintEventKind.RESPONSIBLE_CHANGED) & Q(responsible__isnull=True),
                name="complaint_event_responsible_field",
            ),
        ]

    def __str__(self):
        return f"{self.complaint}: {self.get_kind_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Complaint history cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Complaint history cannot be deleted.")
