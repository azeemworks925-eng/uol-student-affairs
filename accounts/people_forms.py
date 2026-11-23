"""Forms for the Super Admin's People pages. They shape input; the services decide (DEC-330)."""

from django import forms
from django.db.models import Q

from academics.models import Batch, Section, Semester
from dsa.sorting import merge_sort

from .forms import AccessibleErrorsMixin
from .models import User
from .representation import POST_LABELS, POST_NAMES, Cohort, departure_needs_replacement, eligible_candidates


class EntryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, entry):
        return f"{entry} (inactive, current)" if not entry.is_active else str(entry)


def _entries(model, current_id=None):
    """Active entries only, plus the one the record already uses, so saving a name never forces a move."""
    query = Q(is_active=True)
    if current_id:
        query |= Q(pk=current_id)
    return model.objects.filter(query)


def replacement_label(student):
    return f"{student.get_full_name()} ({student.student_profile.sap_id})"


class ReplacementMixin:
    """Adds a "New CR/GR" choice when this person's departure would leave a post vacant (DEC-323).
    The services re-check everything under their locks."""

    def setup_replacement(self, user):
        self.needs_replacement = departure_needs_replacement(user)
        if self.needs_replacement is None:
            return
        period, post, _ = self.needs_replacement
        field = forms.ModelChoiceField(
            queryset=eligible_candidates(Cohort.of(period)), required=False, empty_label="Choose a student",
            label=f"New {POST_LABELS[post]} ({POST_NAMES[post]})",
            help_text=f"This student is the cohort's {POST_LABELS[post]}. The post can't be left vacant.",
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        field.label_from_instance = replacement_label
        self.fields["replacement"] = field
        self.replacement_post = POST_LABELS[post]

    def require_replacement(self, leaving):
        if leaving and self.needs_replacement is not None and not self.cleaned_data.get("replacement"):
            self.add_error("replacement", f"Choose a new {self.replacement_post} first: this change would leave the post vacant.")


class StudentEditForm(ReplacementMixin, AccessibleErrorsMixin, forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))

    def __init__(self, *args, profile, **kwargs):
        kwargs.setdefault("initial", {
            "full_name": profile.user.full_name, "batch": profile.batch_id,
            "semester": profile.semester_id, "section": profile.section_id,
        })
        super().__init__(*args, **kwargs)
        self.profile = profile
        for name, model in (("batch", Batch), ("semester", Semester), ("section", Section)):
            self.fields[name] = EntryChoiceField(
                queryset=_entries(model, getattr(profile, f"{name}_id")), empty_label=None,
                widget=forms.Select(attrs={"class": "form-select"}))
        self.setup_replacement(profile.user)

    @property
    def moving(self):
        data = getattr(self, "cleaned_data", {})
        return any(data.get(name) is not None and data[name].pk != getattr(self.profile, f"{name}_id")
                   for name in ("batch", "semester", "section"))

    def clean(self):
        cleaned = super().clean()
        self.require_replacement(self.moving)
        return cleaned


class NameForm(AccessibleErrorsMixin, forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))


class AccountActiveForm(ReplacementMixin, AccessibleErrorsMixin, forms.Form):
    """Deactivate or reactivate. A replacement is asked for only when deactivating a CR or GR."""

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user.is_active:
            self.setup_replacement(user)
        else:
            self.needs_replacement = None

    def clean(self):
        cleaned = super().clean()
        self.require_replacement(self.user.is_active)
        return cleaned


class StudentAccountForm(AccessibleErrorsMixin, forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))
    email = forms.EmailField(label="Student email", help_text="The eight-digit SAP ID at @student.uol.edu.pk.",
                             widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "off"}))


def active_cohort_choices():
    """Every exact batch + semester + section combination of active entries, in academic order."""
    combos = [(batch, semester, section) for batch in Batch.objects.active() for semester in Semester.objects.active()
              for section in Section.objects.active()]
    ordered = merge_sort(combos, key=lambda c: (c[0].name, c[1].number, c[2].name))
    return [(Cohort(b.pk, s.pk, c.pk).key, f"{b} · {s} · {c}") for b, s, c in ordered]


class StaffCreateForm(AccessibleErrorsMixin, forms.Form):
    role = forms.ChoiceField(choices=[(User.Role.BATCH_ADVISOR, "Batch Advisor"), (User.Role.SUPER_ADMIN, "Super Admin")],
                             widget=forms.HiddenInput)
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))
    email = forms.EmailField(label="Official email", help_text="They sign in with Google using this address. No password is set.",
                             widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "off"}))
    cohorts = forms.MultipleChoiceField(required=False, label="Cohorts", widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cohorts"].choices = active_cohort_choices()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") == User.Role.SUPER_ADMIN:
            cleaned["cohorts"] = []
        return cleaned

    def cohort_values(self):
        return [Cohort.parse(value) for value in self.cleaned_data.get("cohorts", [])]


class AssignmentForm(AccessibleErrorsMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, model, empty in (("batch", Batch, "Choose a batch"), ("semester", Semester, "Choose a semester"),
                                   ("section", Section, "Choose a section")):
            self.fields[name] = forms.ModelChoiceField(queryset=model.objects.active(), empty_label=empty,
                                                       widget=forms.Select(attrs={"class": "form-select"}))

    def cohort(self):
        data = self.cleaned_data
        return Cohort(data["batch"].pk, data["semester"].pk, data["section"].pk)
