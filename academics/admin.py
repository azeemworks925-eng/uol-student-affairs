from django.contrib import admin, messages
from django.db import IntegrityError
from django.http import HttpResponseRedirect

from . import services
from .models import AcademicTerm, Batch, Section, Semester


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


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    """Academic terms (Complaints Part 4 Stage 4a, DEC-314). The Django admin is open only to
    active Super Admins (the role sets is_staff). Terms are never deleted, and the current
    flag is not a form field: it changes only through the two actions, which use
    academics.services (row locks, database-enforced single current term)."""

    list_display = ("name", "start_date", "end_date", "current_label")
    list_display_links = ("name",)
    search_fields = ("name",)
    fields = ("name", "start_date", "end_date", "current_label")
    readonly_fields = ("current_label",)
    actions = ("make_current", "clear_current")

    @admin.display(description="Current term", ordering="is_current")
    def current_label(self, obj):
        return "Current term" if obj and obj.is_current else "Not current"

    def has_delete_permission(self, request, obj=None):
        # DEC-210 pattern: academic records are kept, never deleted.
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # The form already refuses duplicate names (ignoring case and accents) and reversed
        # dates. A duplicate saved by someone else at the same moment is caught by the
        # database; the admin's transaction has rolled back by the time it arrives here.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            self.message_user(
                request,
                "The term was not saved: it conflicts with a term saved at the same time "
                "(for example, the same name). Check the list and try again.",
                messages.ERROR,
            )
            return HttpResponseRedirect(request.get_full_path())

    @admin.action(description="Make the selected term the current term")
    def make_current(self, request, queryset):
        terms = list(queryset[:2])
        if len(terms) != 1:
            self.message_user(request, "Select exactly one term to make it the current term.", messages.ERROR)
            return
        term = terms[0]
        try:
            previous, changed = services.set_current_term(term)
        except (services.CurrentTermConflict, AcademicTerm.DoesNotExist) as exc:
            self.message_user(request, f"No change was made. {exc}", messages.ERROR)
            return
        if not changed:
            self.message_user(request, f"{term} is already the current term.", messages.INFO)
        elif previous:
            self.message_user(request, f"{term} is now the current term (it replaces {previous}).", messages.SUCCESS)
        else:
            self.message_user(request, f"{term} is now the current term.", messages.SUCCESS)

    @admin.action(description="Clear the current term (select the current term only)")
    def clear_current(self, request, queryset):
        terms = list(queryset[:2])
        if len(terms) != 1 or not terms[0].is_current:
            self.message_user(
                request, "To clear the current term, select the current term and nothing else.", messages.ERROR
            )
            return
        term = terms[0]
        try:
            services.clear_current_term(expected=term)
        except services.CurrentTermChanged as exc:
            now = exc.args[0] if exc.args else None
            detail = f"{now} is now the current term." if now else "No term is current now."
            self.message_user(request, f"No change was made: the current term changed at the same time. {detail}", messages.ERROR)
            return
        except services.CurrentTermConflict as exc:
            self.message_user(request, f"No change was made. {exc}", messages.ERROR)
            return
        self.message_user(
            request,
            f"{term} is no longer the current term. No term is current now.",
            messages.SUCCESS,
        )
