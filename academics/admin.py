from django.contrib import admin

from .models import Batch, Section, Semester


class AcademicEntryAdmin(admin.ModelAdmin):
    list_filter = ("is_active",)
    list_editable = ("is_active",)

    def has_delete_permission(self, request, obj=None):
        # DEC-210: entries are deactivated, never deleted, to preserve history.
        return False


@admin.register(Batch)
class BatchAdmin(AcademicEntryAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)


@admin.register(Semester)
class SemesterAdmin(AcademicEntryAdmin):
    list_display = ("number", "is_active")


@admin.register(Section)
class SectionAdmin(AcademicEntryAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
