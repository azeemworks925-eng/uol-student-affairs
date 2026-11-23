"""
Meetings (DEC-060, DEC-260 to DEC-263, DEC-328).

- Meeting: one row per meeting, holding its current status and time.
- MeetingEvent: the permanent history. Each step is one row, so one meeting can send several
  notifications (the notifications table allows one per source record).

The cohort (batch + semester + section) is copied from the student's profile when the meeting is
created and never changes, so it stays with the advisors of that exact cohort (DEC-205).

Changes go through meetings.services. Records cannot be deleted, and the ORM refuses bulk changes.
Raw SQL is outside what Django can protect.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models
from django.db.models import Q

REASON_MIN = 10
REASON_MAX = 500
NOTE_MAX = 300
LOCATION_MAX = 120
DURATIONS = (15, 30, 45, 60)
REASON_MESSAGE = f"Write between {REASON_MIN} and {REASON_MAX} characters."

# These never change after the meeting is created.
FROZEN_FIELDS = ("student_id", "batch_id", "semester_id", "section_id", "reason", "preferred_at")


class ProtectedMeetingError(ValidationError):
    """An attempt to change or delete a meeting record outside meetings.services."""


class ProtectedQuerySet(models.QuerySet):
    """Refuses the bulk operations that would skip save() and delete()."""

    def update(self, **kwargs):
        raise ProtectedMeetingError("Meetings cannot be bulk-updated. Use meetings.services.")

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        raise ProtectedMeetingError("Meetings cannot be bulk-updated. Use meetings.services.")

    bulk_update.alters_data = True

    def delete(self):
        raise ProtectedMeetingError("Meeting records cannot be deleted.")

    delete.alters_data = True
    delete.queryset_only = True

    def bulk_create(self, objs, *args, update_conflicts=False, **kwargs):
        if update_conflicts:
            raise ProtectedMeetingError("Meeting records cannot be overwritten by bulk_create.")
        return super().bulk_create(objs, *args, **kwargs)

    bulk_create.alters_data = True


class Meeting(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        TIME_SUGGESTED = "time_suggested", "Time suggested"
        CONFIRMED = "confirmed", "Confirmed"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="meetings",
        limit_choices_to={"role": "student"},
    )
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="meetings")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="meetings")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="meetings")
    # The advisor who confirmed or suggested a time. Empty while the request is open to the cohort's advisors.
    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="advised_meetings",
        limit_choices_to={"role": "batch_advisor"},
    )
    reason = models.TextField(
        max_length=REASON_MAX,
        validators=[MinLengthValidator(REASON_MIN, REASON_MESSAGE), MaxLengthValidator(REASON_MAX, REASON_MESSAGE)],
    )
    preferred_at = models.DateTimeField(null=True, blank=True)  # empty when an advisor scheduled it directly
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REQUESTED)
    # The confirmed or suggested time.
    starts_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=LOCATION_MAX, blank=True)
    suggestion_note = models.TextField(max_length=NOTE_MAX, blank=True)
    closed_reason = models.TextField(max_length=NOTE_MAX, blank=True)  # why it was declined or cancelled
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProtectedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["batch", "semester", "section", "status"], name="meeting_cohort_status_idx"),
            models.Index(fields=["student", "status"], name="meeting_student_status_idx"),
            models.Index(fields=["advisor", "status", "starts_at"], name="meeting_advisor_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["requested", "time_suggested", "confirmed", "declined", "cancelled"]),
                name="meeting_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__isnull=True) | Q(duration_minutes__in=DURATIONS),
                name="meeting_duration_valid",
            ),
            # A suggested or confirmed meeting always has a time, an advisor and a place.
            models.CheckConstraint(
                condition=~Q(status__in=["time_suggested", "confirmed"])
                | (Q(starts_at__isnull=False, duration_minutes__isnull=False, advisor__isnull=False) & ~Q(location="")),
                name="meeting_agreed_has_slot",
            ),
            models.CheckConstraint(
                condition=~Q(status="cancelled") | ~Q(closed_reason=""),
                name="meeting_cancelled_has_reason",
            ),
        ]

    def __str__(self):
        return f"Meeting #{self.pk} ({self.get_status_display()})"

    @property
    def when(self):
        """The agreed or suggested time, otherwise the student's preferred time."""
        return self.starts_at or self.preferred_at

    @property
    def ends_at(self):
        if self.starts_at is None or self.duration_minutes is None:
            return None
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_requested(self):
        return self.status == self.Status.REQUESTED

    @property
    def is_time_suggested(self):
        return self.status == self.Status.TIME_SUGGESTED

    @property
    def is_confirmed(self):
        return self.status == self.Status.CONFIRMED

    @property
    def is_final(self):
        return self.status in (self.Status.DECLINED, self.Status.CANCELLED)

    def save(self, *args, **kwargs):
        # Compare with the stored row, not in-memory state, so a rebuilt object cannot overwrite it.
        if self.pk is not None and not kwargs.get("force_insert"):
            stored = Meeting._base_manager.filter(pk=self.pk).values(*FROZEN_FIELDS, "status").first()
            if stored:
                if any(stored[field] != getattr(self, field) for field in FROZEN_FIELDS):
                    raise ProtectedMeetingError("A meeting's student, cohort and reason cannot be changed.")
                if stored["status"] in (self.Status.DECLINED, self.Status.CANCELLED) and stored["status"] != self.status:
                    raise ProtectedMeetingError("A declined or cancelled meeting is final.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedMeetingError("Meeting records cannot be deleted.")


class MeetingEvent(models.Model):
    """One step in a meeting's history. Written once."""

    class Kind(models.TextChoices):
        REQUESTED = "requested", "Requested"
        SCHEDULED = "scheduled", "Scheduled by advisor"
        SUGGESTED = "suggested", "Time suggested"
        CONFIRMED = "confirmed", "Confirmed"
        ACCEPTED = "accepted", "Suggested time accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    meeting = models.ForeignKey(Meeting, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(max_length=NOTE_MAX, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProtectedQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["meeting", "created_at"], name="meeting_event_recent_idx")]

    def __str__(self):
        return f"{self.get_kind_display()} on meeting #{self.meeting_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None and MeetingEvent._base_manager.filter(pk=self.pk).exists():
            raise ProtectedMeetingError("Meeting history cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedMeetingError("Meeting history cannot be deleted.")
