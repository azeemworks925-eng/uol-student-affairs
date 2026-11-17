"""
Complaints (DEC-030, DEC-031, DEC-220 to DEC-230).

A complaint belongs to the student who submitted it and records the exact cohort
(batch + semester + section, DEC-205) the student was in at submission. Every change is an
immutable ComplaintEvent, so the original description and the full history are never lost
(DEC-223). Records are never deleted: foreign keys use PROTECT, and academic structure and
categories are deactivated rather than deleted (DEC-210).

State changes go through complaints.services; access is decided by complaints.permissions.

Protection covers Django's ordinary ORM paths: instance save()/delete() and the bulk
QuerySet operations (update, bulk_update, delete and upserting bulk_create). It does not, and
cannot, stop raw SQL or direct database access.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models import Q

from academics.models import ActiveQuerySet

# TextField max_length is not checked by full_clean(), so the limit is also a validator.
TEXT_LIMIT = 5000


class ProtectedRecordError(ValidationError):
    """An attempt to change or delete a complaint record outside the complaint services."""


class ProtectedQuerySet(models.QuerySet):
    """
    Refuses the bulk operations that skip Model.save() and Model.delete().

    Inserts (create, bulk_create without upsert) are allowed. Legitimate changes go through
    complaints.services, which save individual instances: Model.save() updates the row with
    Django's internal QuerySet._update(), not update(), so it is not affected.
    """

    def update(self, **kwargs):
        raise ProtectedRecordError(
            f"{self.model._meta.verbose_name_plural.capitalize()} cannot be bulk-updated. "
            "Use complaints.services."
        )

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        raise ProtectedRecordError(f"{self.model._meta.verbose_name_plural.capitalize()} cannot be bulk-updated.")

    bulk_update.alters_data = True

    def delete(self):
        raise ProtectedRecordError(f"{self.model._meta.verbose_name_plural.capitalize()} cannot be deleted.")

    delete.alters_data = True
    delete.queryset_only = True

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        if update_conflicts:
            # An upsert would overwrite existing rows.
            raise ProtectedRecordError(
                f"{self.model._meta.verbose_name_plural.capitalize()} cannot be overwritten by bulk_create."
            )
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields, unique_fields=unique_fields,
        )

    bulk_create.alters_data = True


class CategoryQuerySet(ActiveQuerySet):
    """Categories and subcategories are deactivated, never deleted (DEC-210, Part 4 section 4).
    Bulk delete() is refused; update() stays available."""

    def delete(self):
        raise ProtectedRecordError(
            f"{self.model._meta.verbose_name_plural.capitalize()} cannot be deleted. Deactivate them instead."
        )

    delete.alters_data = True
    delete.queryset_only = True


class ComplaintCategory(models.Model):
    """A main complaint category, managed by the Super Admin (DEC-220; changes through
    complaints.category_services)."""

    name = models.CharField(max_length=80, unique=True)
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers are listed first.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "complaint categories"

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        raise ProtectedRecordError("Complaint categories cannot be deleted. Deactivate them instead.")


class ComplaintSubcategory(models.Model):
    """An optional subcategory within a main category (DEC-220). Its parent is fixed at
    creation: moving it would reclassify the complaints that use it."""

    category = models.ForeignKey(ComplaintCategory, on_delete=models.PROTECT, related_name="subcategories")
    name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers are listed first.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["category__position", "category__name", "position", "name"]
        verbose_name_plural = "complaint subcategories"
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_name_per_category")
        ]

    def __str__(self):
        return f"{self.category} / {self.name}"

    def save(self, *args, **kwargs):
        # Compare with the stored row (not in-memory state), as for complaint descriptions.
        update_fields = kwargs.get("update_fields")
        writes_parent = update_fields is None or "category" in update_fields or "category_id" in update_fields
        if self.pk is not None and writes_parent and not kwargs.get("force_insert"):
            stored = ComplaintSubcategory._base_manager.filter(pk=self.pk).values_list("category_id", flat=True).first()
            if stored is not None and stored != self.category_id:
                raise ProtectedRecordError("A subcategory cannot be moved to another category.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedRecordError("Complaint subcategories cannot be deleted. Deactivate them instead.")


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

    objects = ProtectedQuerySet.as_manager()

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

    def clean(self):
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "This subcategory does not belong to the chosen category."})

    def save(self, *args, **kwargs):
        # Compare with the stored row, not with in-memory state: a newly constructed instance
        # given an existing primary key would otherwise overwrite the original (DEC-223).
        # The services always pass update_fields without "description", so they skip the query.
        update_fields = kwargs.get("update_fields")
        writes_description = update_fields is None or "description" in update_fields
        if self.pk is not None and writes_description and not kwargs.get("force_insert"):
            stored = Complaint._base_manager.filter(pk=self.pk).values_list("description", flat=True).first()
            if stored is not None and stored != self.description:
                raise ProtectedRecordError("A complaint's original description cannot be changed (DEC-223).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedRecordError("Complaints cannot be deleted (DEC-224).")

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

    objects = ProtectedQuerySet.as_manager()

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
        # History is insert-only. _state.adding alone is not enough: a newly constructed
        # instance given an existing primary key also has adding=True, and Django would
        # UPDATE that row. So refuse partial saves and existing primary keys, and always
        # INSERT (a duplicate key racing in between then fails in the database).
        if not self._state.adding or kwargs.get("update_fields") is not None or (
            self.pk is not None and ComplaintEvent._base_manager.filter(pk=self.pk).exists()
        ):
            raise ProtectedRecordError("Complaint history cannot be changed.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedRecordError("Complaint history cannot be deleted.")
