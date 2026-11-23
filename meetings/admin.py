from django.contrib import admin

from .models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    """Read-only: changes happen only through meetings.services."""

    list_display = ("id", "status", "student", "advisor", "starts_at", "batch", "semester", "section")
    list_filter = ("status", "batch", "semester", "section")
    list_select_related = ("student", "advisor", "batch", "semester", "section")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
