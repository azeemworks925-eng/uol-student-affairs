"""
In-app notifications (DEC-070, DEC-270; COMPLAINTS_PART4_SPEC.md section 5).

A reusable foundation: one recipient per notification, a registered event type, the identity of
the immutable source record that caused it, a concise title and body, and an allowlisted internal
destination stored as a route name and argument (never a URL). Content is written once; only
`read_at` (NULL = unread) can change, and only through notifications.services.

Protection covers Django's ordinary ORM paths (instance save, update, bulk_update and upserting
bulk_create), as for the complaint models. It does not, and cannot, stop raw SQL.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

READ_STATE_FIELDS = frozenset({"read_at"})


class ProtectedNotificationError(ValidationError):
    """An attempt to change a notification's content (only read_at may change)."""


class NotificationQuerySet(models.QuerySet):
    """Inserts are allowed; on existing rows only read_at may be updated."""

    def update(self, **kwargs):
        if not set(kwargs) <= READ_STATE_FIELDS:
            raise ProtectedNotificationError("Notifications cannot be changed; only their read state can.")
        return super().update(**kwargs)

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        if not set(fields) <= READ_STATE_FIELDS:
            raise ProtectedNotificationError("Notifications cannot be changed; only their read state can.")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    bulk_update.alters_data = True

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        if update_conflicts:
            # An upsert would overwrite an existing notification.
            raise ProtectedNotificationError("Notifications cannot be overwritten by bulk_create.")
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields, unique_fields=unique_fields,
        )

    bulk_create.alters_data = True


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    # A key in notifications.registry, for example "complaint.response".
    event_type = models.CharField(max_length=64)
    # The source record (model label, for example "complaints.complaintevent", and its pk).
    source_type = models.CharField(max_length=64)
    source_id = models.PositiveBigIntegerField()
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=300, blank=True)
    # An allowlisted route name and its single argument, reversed only when opened.
    target_url_name = models.CharField(max_length=100)
    target_arg = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # One notification per recipient per source record (retries, double calls, races).
            models.UniqueConstraint(
                fields=["recipient", "source_type", "source_id"], name="unique_notification_per_recipient_source"
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "read_at"], name="notification_unread_idx"),
            models.Index(fields=["recipient", "-created_at"], name="notification_recent_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} for {self.recipient_id}: {self.title}"

    @property
    def is_read(self):
        return self.read_at is not None

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # Updating an existing row: only the read state.
            if not set(update_fields) <= READ_STATE_FIELDS:
                raise ProtectedNotificationError("Notifications cannot be changed; only their read state can.")
            return super().save(*args, **kwargs)
        # Otherwise only a new row. _state.adding is not enough: a newly constructed object given
        # an existing primary key is also "adding", and Django would UPDATE that row.
        if not self._state.adding or (
            self.pk is not None and Notification._base_manager.filter(pk=self.pk).exists()
        ):
            raise ProtectedNotificationError("Notifications cannot be changed; only their read state can.")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)
