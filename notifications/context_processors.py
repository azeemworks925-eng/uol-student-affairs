"""Header unread count for the signed-in user. Lazy: the single indexed COUNT runs only when a
template (the application layout) reads it, so sign-in pages and others never query."""

from django.utils.functional import cached_property

from . import services

LATEST_LIMIT = 5


class UnreadNotifications:
    def __init__(self, user):
        self._user = user

    @cached_property
    def count(self):
        return services.unread_count(self._user)

    @cached_property
    def latest(self):
        """The newest few, for the bell's dropdown."""
        return list(services.for_user(self._user)[:LATEST_LIMIT])

    @property
    def display(self):
        return f"{services.UNREAD_DISPLAY_CAP}+" if self.count > services.UNREAD_DISPLAY_CAP else str(self.count)

    @property
    def label(self):
        """Accessible name for the header entry point."""
        if not self.count:
            return "Notifications, none unread"
        return f"Notifications, {self.count} unread"


def notifications(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.is_active):
        return {}
    return {"sa_notifications": UnreadNotifications(user)}
