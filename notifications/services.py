"""
Notification operations.

Producers call `notify` from inside their own atomic transaction, so a notification commits or
rolls back with the action that caused it. `notify` does not check whether the recipient is
active: a deactivated user's notifications are kept for when they are reactivated, and inactive
users cannot sign in to see them. Everything a user does with notifications (count, list, open,
mark read) requires an authenticated, active user and is scoped to their own notifications.
"""

from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import Truncator

from . import registry
from .models import Notification

TITLE_LIMIT = Notification._meta.get_field("title").max_length
BODY_LIMIT = Notification._meta.get_field("body").max_length
UNREAD_DISPLAY_CAP = 9  # the header shows "9+" above this


def _active(user):
    return bool(user and user.is_authenticated and user.is_active)


def notify(recipient, *, event_type, source, title, body="", target_url_name, target_arg=""):
    """
    Create the notification for one recipient and one saved source record, or return the existing
    one (the database allows only one per recipient and source). Returns (notification, created).
    """
    notification_type = registry.get_type(event_type)
    if notification_type is None:
        raise ValidationError(f"Unregistered notification type: {event_type}.")
    if source is None or getattr(source, "pk", None) is None:
        raise ValidationError("A notification needs a saved source record.")
    source_type = source._meta.label_lower
    if source_type != notification_type.source_model:
        raise ValidationError(f"{event_type} notifications come from {notification_type.source_model}, not {source_type}.")
    if target_url_name not in notification_type.destinations:
        raise ValidationError(f"{target_url_name} is not an allowed destination for {event_type}.")
    if recipient is None or getattr(recipient, "pk", None) is None:
        raise ValidationError("A notification needs a saved recipient.")
    reverse(target_url_name, args=[target_arg] if target_arg else [])  # fail now, not when opened

    # get_or_create uses a savepoint, so a concurrent duplicate never breaks the caller's
    # transaction: it returns the row the other writer created.
    return Notification.objects.get_or_create(
        recipient=recipient,
        source_type=source_type,
        source_id=source.pk,
        defaults={
            "event_type": event_type,
            "title": Truncator(title).chars(TITLE_LIMIT),
            "body": Truncator(body or "").chars(BODY_LIMIT),
            "target_url_name": target_url_name,
            "target_arg": target_arg,
        },
    )


# ---------- What a user does with their own notifications ----------

def for_user(user):
    """The user's own notifications, newest first; none for anonymous or inactive users."""
    if not _active(user):
        return Notification.objects.none()
    return Notification.objects.filter(recipient=user)


def unread_count(user):
    return for_user(user).filter(read_at__isnull=True).count()


def mark_read(user, notification_id):
    """Mark one of the user's own notifications read. Idempotent: the first read time is kept.
    Returns the notification, or None if it is not the user's (or does not exist)."""
    notification = for_user(user).filter(pk=notification_id).first()
    if notification is None:
        return None
    for_user(user).filter(pk=notification.pk, read_at__isnull=True).update(read_at=timezone.now())
    notification.refresh_from_db(fields=["read_at"])
    return notification


def mark_all_read(user):
    return for_user(user).filter(read_at__isnull=True).update(read_at=timezone.now())


def destination_url(notification):
    """The internal URL to open, or None if the stored destination is not allowed or no longer
    resolves. Built only from the registry and reverse(); nothing from the request."""
    if not registry.is_allowed_destination(notification.event_type, notification.target_url_name):
        return None
    try:
        return reverse(notification.target_url_name, args=[notification.target_arg] if notification.target_arg else [])
    except NoReverseMatch:
        return None
