"""
Section Issues, also called Collective Issues (DEC-040, DEC-240 to DEC-247, DEC-324, DEC-325).

Three tables:
- CollectiveIssue: what a CR or GR published for their exact cohort. The content never changes.
- Support: one row per student who supported an issue. The count is always counted from here,
  so there is no separate counter that could drift.
- IssueEvent: the append-only history (raised, status changed, official response).

Changes go through issues.services. The ORM refuses bulk changes and deletes. Raw SQL is outside
what Django can protect, but the database constraints below still apply to it.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual

TITLE_MIN = 5
TITLE_MAX = 120
DESCRIPTION_MIN = 20
DESCRIPTION_MAX = 2000
RESPONSE_MAX = 1000

# These never change after publication (DEC-242, DEC-324).
FROZEN_FIELDS = ("batch_id", "semester_id", "section_id", "raised_by_id", "raised_as", "title", "description")


class ProtectedIssueError(ValidationError):
    """An attempt to change or delete a section issue record outside issues.services."""


def _length_between(field, low, high):
    """A database check that counts characters, not bytes."""
    return Q(GreaterThanOrEqual(Length(field), low), LessThanOrEqual(Length(field), high))


class ProtectedQuerySet(models.QuerySet):
    """Refuses the bulk operations that would skip save() and delete()."""

    def update(self, **kwargs):
        raise ProtectedIssueError("Section issue records cannot be bulk-updated. Use issues.services.")

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        raise ProtectedIssueError("Section issue records cannot be bulk-updated. Use issues.services.")

    bulk_update.alters_data = True

    def delete(self):
        raise ProtectedIssueError("Section issue records cannot be deleted.")

    delete.alters_data = True
    delete.queryset_only = True

    def bulk_create(self, objs, *args, update_conflicts=False, **kwargs):
        if update_conflicts:
            raise ProtectedIssueError("Section issue records cannot be overwritten.")
        return super().bulk_create(objs, *args, **kwargs)

    bulk_create.alters_data = True


class InsertOnlyModel(models.Model):
    """A row that can be created once and never changed or deleted."""

    objects = ProtectedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # A new object given an existing primary key would otherwise UPDATE that row.
        if not self._state.adding or kwargs.get("update_fields") is not None or (
            self.pk is not None and type(self)._base_manager.filter(pk=self.pk).exists()
        ):
            raise ProtectedIssueError("This record cannot be changed.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedIssueError("This record cannot be deleted.")


class CollectiveIssue(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        UNDER_REVIEW = "under_review", "Under Review"
        RESOLVED = "resolved", "Resolved"

    class Post(models.TextChoices):
        CR = "cr", "CR"
        GR = "gr", "GR"

    # CI-<year>-<5 digits>, from the primary key inside the publishing transaction. It is empty
    # only for the instant between the insert and that update.
    reference = models.CharField(max_length=20, unique=True, null=True, editable=False)
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="collective_issues")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="collective_issues")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="collective_issues")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="raised_issues")
    raised_as = models.CharField(max_length=2, choices=Post.choices)  # the post held when publishing
    title = models.CharField(max_length=TITLE_MAX)
    description = models.TextField(max_length=DESCRIPTION_MAX)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    # Set once, by the first official response or the resolution. It is the moment support closed.
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(max_length=RESPONSE_MAX, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProtectedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "section issue"
        indexes = [
            models.Index(fields=["batch", "semester", "section", "status"], name="issue_cohort_status_idx"),
            models.Index(fields=["batch", "semester", "section", "-created_at"], name="issue_cohort_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=_length_between("title", TITLE_MIN, TITLE_MAX),
                                   name="collective_issue_title_length"),
            models.CheckConstraint(condition=_length_between("description", DESCRIPTION_MIN, DESCRIPTION_MAX),
                                   name="collective_issue_description_length"),
            models.CheckConstraint(condition=Q(status__in=["received", "under_review", "resolved"]),
                                   name="collective_issue_status_valid"),
            models.CheckConstraint(condition=Q(raised_as__in=["cr", "gr"]), name="collective_issue_post_valid"),
            # A resolved issue always has its note and time; an open one has neither.
            models.CheckConstraint(
                condition=Q(resolution_note="", resolved_at__isnull=True, status__in=["received", "under_review"])
                | (Q(resolved_at__isnull=False, status="resolved")
                   & _length_between("resolution_note", 1, RESPONSE_MAX)),
                name="collective_issue_resolution_consistent",
            ),
            models.CheckConstraint(condition=~Q(status="resolved") | Q(first_response_at__isnull=False),
                                   name="collective_issue_resolved_was_answered"),
        ]

    def __str__(self):
        return self.reference or f"Issue #{self.pk}"

    @property
    def cohort_is_active(self):
        return self.batch.is_active and self.semester.is_active and self.section.is_active

    @property
    def support_is_open(self):
        """Open until the first official response or resolution, in an active cohort only."""
        return self.first_response_at is None and self.cohort_is_active

    def save(self, *args, **kwargs):
        # Compare with the stored row, so a rebuilt object cannot overwrite the original.
        if self.pk is not None and not kwargs.get("force_insert"):
            stored = CollectiveIssue._base_manager.filter(pk=self.pk).values(*FROZEN_FIELDS, "status").first()
            if stored:
                if any(stored[field] != getattr(self, field) for field in FROZEN_FIELDS):
                    raise ProtectedIssueError("A published issue cannot be edited.")
                if stored["status"] == self.Status.RESOLVED:
                    raise ProtectedIssueError("A resolved issue is final.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedIssueError("A published issue cannot be deleted.")


class Support(InsertOnlyModel):
    """One student's support. Identities are never shown in the interface, only the count."""

    issue = models.ForeignKey(CollectiveIssue, on_delete=models.PROTECT, related_name="supports")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issue_supports")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issue", "student"], name="unique_support_per_student")]

    def __str__(self):
        return f"Support #{self.pk}"


class IssueEvent(InsertOnlyModel):
    """One immutable entry in an issue's history."""

    class Kind(models.TextChoices):
        RAISED = "raised", "Raised"
        STATUS_CHANGED = "status_changed", "Status changed"
        RESPONSE = "response", "Official response"

    issue = models.ForeignKey(CollectiveIssue, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=20, choices=CollectiveIssue.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=CollectiveIssue.Status.choices, blank=True)
    message = models.TextField(max_length=RESPONSE_MAX, blank=True)  # a response or resolution note
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["issue", "created_at"], name="issue_event_timeline_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=["raised", "status_changed", "response"]),
                                   name="issue_event_kind_valid"),
            # A response or a resolution carries a message; every other event has none.
            models.CheckConstraint(
                condition=(Q(kind="response") | Q(kind="status_changed", to_status="resolved"))
                & _length_between("message", 1, RESPONSE_MAX)
                | (Q(kind="raised") | (Q(kind="status_changed") & ~Q(to_status="resolved"))) & Q(message=""),
                name="issue_event_message_rule",
            ),
        ]

    def __str__(self):
        return f"{self.issue}: {self.get_kind_display()}"

    @property
    def is_resolution(self):
        return self.kind == self.Kind.STATUS_CHANGED and self.to_status == CollectiveIssue.Status.RESOLVED
