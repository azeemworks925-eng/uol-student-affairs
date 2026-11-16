"""
Django admin for accounts. Only the Super Admin can use it (review M1: only that role
holds is_staff), and it is the interim management interface until the portal dashboards
are designed.

Accounts have no passwords: every role signs in with Google (DEC-010). Accounts are
deactivated, never deleted (DEC-212).
"""

from django import forms
from django.contrib import admin

from allauth.socialaccount.models import SocialAccount

from .models import AdvisorAssignment, StudentProfile, StudentProfileChange, User
from .services import record_profile_changes


class NoDeleteMixin:
    def has_delete_permission(self, request, obj=None):
        return False


class PortalUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "full_name", "role", "is_active")


class AdvisorAssignmentInline(admin.TabularInline):
    model = AdvisorAssignment
    fk_name = "advisor"
    fields = ("batch", "semester", "section", "assigned_by", "created_at")
    readonly_fields = ("assigned_by", "created_at")
    extra = 1


@admin.register(User)
class UserAdmin(NoDeleteMixin, admin.ModelAdmin):
    form = PortalUserForm
    list_display = ("email", "full_name", "role", "is_active", "google_sign_in", "date_joined")
    list_filter = ("role", "is_active")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "full_name", "role", "is_active")}),
        ("Status", {"fields": ("google_sign_in", "is_staff", "is_superuser", "last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "full_name", "role")}),)

    @admin.display(description="Google sign-in")
    def google_sign_in(self, obj):
        if obj.pk and SocialAccount.objects.filter(user=obj).exists():
            return "Linked"
        return "Not signed in yet"

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = ["google_sign_in", "is_staff", "is_superuser", "last_login", "date_joined"]
        if obj is not None:
            # The email is the Google identity and the role defines the account type;
            # neither changes after creation.
            readonly += ["email", "role"]
        return readonly

    def get_inlines(self, request, obj):
        return [AdvisorAssignmentInline] if obj is not None and obj.is_batch_advisor else []

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        elif obj.is_student and "full_name" in form.changed_data and hasattr(obj, "student_profile"):
            record_profile_changes(
                obj.student_profile, {"full_name": (form.initial.get("full_name"), obj.full_name)}, request.user
            )
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        for assignment in formset.save(commit=False):
            if assignment.assigned_by_id is None:
                assignment.assigned_by = request.user
            assignment.save()
        for assignment in formset.deleted_objects:
            assignment.delete()
        formset.save_m2m()


@admin.register(StudentProfile)
class StudentProfileAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("sap_id", "student_name", "student_email", "batch", "semester", "section", "is_active")
    list_filter = ("semester", "section", "batch", "user__is_active")
    search_fields = ("sap_id", "user__email", "user__full_name")
    fields = ("user", "sap_id", "department", "batch", "semester", "section", "created_at", "updated_at")
    readonly_fields = ("user", "sap_id", "department", "created_at", "updated_at")
    list_select_related = ("user", "batch", "semester", "section")

    AUDITED_FIELDS = ("batch", "semester", "section")

    @admin.display(description="Name", ordering="user__full_name")
    def student_name(self, obj):
        return obj.user.full_name

    @admin.display(description="Email", ordering="user__email")
    def student_email(self, obj):
        return obj.user.email

    @admin.display(boolean=True, description="Active", ordering="user__is_active")
    def is_active(self, obj):
        return obj.user.is_active

    def has_add_permission(self, request):
        return False  # Profiles are created only by student registration.

    def save_model(self, request, obj, form, change):
        if change:
            previous = StudentProfile.objects.get(pk=obj.pk)
            record_profile_changes(
                obj,
                {
                    field: (getattr(previous, field), getattr(obj, field))
                    for field in self.AUDITED_FIELDS
                    if field in form.changed_data
                },
                request.user,
            )
        super().save_model(request, obj, form, change)


@admin.register(AdvisorAssignment)
class AdvisorAssignmentAdmin(admin.ModelAdmin):
    list_display = ("advisor", "batch", "semester", "section", "assigned_by", "created_at")
    list_filter = ("batch", "semester", "section")
    search_fields = ("advisor__email", "advisor__full_name")
    fields = ("advisor", "batch", "semester", "section", "assigned_by", "created_at")
    list_select_related = ("advisor", "batch", "semester", "section", "assigned_by")
    readonly_fields = ("assigned_by", "created_at")

    def save_model(self, request, obj, form, change):
        if obj.assigned_by_id is None:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StudentProfileChange)
class StudentProfileChangeAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("changed_at", "profile", "field_name", "old_value", "new_value", "changed_by")
    list_filter = ("field_name",)
    search_fields = ("profile__sap_id", "profile__user__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # The audit trail is read-only.
