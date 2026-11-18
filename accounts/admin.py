"""
Django admin for accounts. Only the Super Admin can use it (review M1: only that role
holds is_staff), and it is the interim management interface until the portal dashboards
are designed.

Accounts have no passwords: every role signs in with Google (DEC-010). Accounts are
deactivated, never deleted (DEC-212).
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect

from allauth.socialaccount.models import SocialAccount

from .models import AdvisorAssignment, StudentProfile, StudentProfileChange, User
from .representation import POST_LABELS, POST_NAMES, departure_needs_replacement, eligible_candidates
from .representation import Cohort as _Cohort
from .services import record_profile_changes, set_account_active, update_student_profile


class ReplacementFieldMixin:
    """A "New CR/GR" choice, offered when this change would take a CR or GR out of an active,
    represented cohort that keeps two or more other active students (DEC-323). The services
    decide under their locks; this gives the form a clear field and message."""

    def _setup_replacement(self, user):
        self.needs_replacement = departure_needs_replacement(user)
        field = self.fields.get("replacement")
        if field is None:
            return
        if self.needs_replacement is None:
            field.queryset = User.objects.none()
            return
        period, post, _ = self.needs_replacement
        field.queryset = eligible_candidates(_Cohort.of(period))
        field.label = f"New {POST_LABELS[post]} ({POST_NAMES[post]}) for {period.batch} · {period.semester} · {period.section}"
        field.help_text = (f"This student is the cohort's {POST_LABELS[post]}. A representative post can't be left "
                           "vacant: choose who takes it over in the same change.")
        field.label_from_instance = lambda student: f"{student.get_full_name()} ({student.student_profile.sap_id})"

    def _require_replacement_if(self, leaving):
        if leaving and self.needs_replacement is not None and not self.cleaned_data.get("replacement"):
            _, post, _ = self.needs_replacement
            self.add_error("replacement", f"Choose a new {POST_LABELS[post]} first: this change would leave the post vacant.")


class ServiceErrorsAdminMixin:
    """A refusal raised by the services while saving (for example, a concurrent change found
    under the locks) is reported as a message; the admin's transaction has rolled back."""

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as error:
            self.message_user(request, "Nothing was saved. " + " ".join(error.messages), messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())


class NoDeleteMixin:
    def has_delete_permission(self, request, obj=None):
        return False


class PortalUserForm(ReplacementFieldMixin, forms.ModelForm):
    replacement = forms.ModelChoiceField(queryset=User.objects.none(), required=False)

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_replacement(self.instance if self.instance.pk else None)

    def clean(self):
        cleaned = super().clean()
        user = self.instance
        self._require_replacement_if(bool(user.pk) and "is_active" in self.fields and not cleaned.get("is_active", True))
        if user.pk and user.is_super_admin and "is_active" in self.fields and not cleaned.get("is_active", True):
            others_active = User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).exclude(pk=user.pk)
            if not others_active.exists():
                # Otherwise no one could manage the portal, and bootstrap_super_admin refuses
                # while any Super Admin account exists.
                self.add_error("is_active", "The last active Super Admin cannot be deactivated.")
        return cleaned


class AdvisorAssignmentInline(admin.TabularInline):
    model = AdvisorAssignment
    fk_name = "advisor"
    fields = ("batch", "semester", "section", "assigned_by", "created_at")
    readonly_fields = ("assigned_by", "created_at")
    extra = 1


@admin.register(User)
class UserAdmin(ServiceErrorsAdminMixin, NoDeleteMixin, admin.ModelAdmin):
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
        if obj is None:
            return self.add_fieldsets
        if departure_needs_replacement(obj) is not None:
            return (*self.fieldsets, ("Representative post", {"fields": ("replacement",)}))
        return self.fieldsets

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
        if change and "is_active" in form.changed_data:
            # Through the lifecycle service: the last-Super-Admin rule and DEC-323 (replacement,
            # refusal or closure) apply in this same transaction.
            set_account_active(obj, obj.is_active, actor=request.user, replacement=form.cleaned_data.get("replacement"))
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


class StudentProfileAdminForm(ReplacementFieldMixin, forms.ModelForm):
    replacement = forms.ModelChoiceField(queryset=User.objects.none(), required=False)

    class Meta:
        model = StudentProfile
        fields = ("batch", "semester", "section")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_replacement(self.instance.user if self.instance.pk else None)

    def clean(self):
        cleaned = super().clean()
        moving = self.instance.pk is not None and any(field in self.changed_data for field in ("batch", "semester", "section"))
        self._require_replacement_if(moving)
        return cleaned


@admin.register(StudentProfile)
class StudentProfileAdmin(ServiceErrorsAdminMixin, NoDeleteMixin, admin.ModelAdmin):
    form = StudentProfileAdminForm
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

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if obj is None or departure_needs_replacement(obj.user) is None:
            fields = [field for field in fields if field != "replacement"]
        elif "replacement" not in fields:
            fields.append("replacement")
        return fields

    def save_model(self, request, obj, form, change):
        # Through the lifecycle service: the change, its audit (DEC-211) and DEC-323
        # (replacement, refusal or closure) commit or roll back together.
        changes = {field: getattr(obj, field) for field in self.AUDITED_FIELDS if field in form.changed_data}
        if change and changes:
            update_student_profile(obj, changes, actor=request.user, replacement=form.cleaned_data.get("replacement"))


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
