from django.contrib import admin

from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """Read-only: changes happen only through voice.services."""

    list_display = ("id", "type", "status", "student", "batch", "semester", "section", "created_at")
    list_filter = ("type", "status", "batch", "semester", "section")
    list_select_related = ("student", "batch", "semester", "section")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
