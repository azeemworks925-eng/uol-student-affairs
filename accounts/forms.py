from django import forms

from academics.models import Batch, Section, Semester


class AccessibleErrorsMixin:
    """Mark invalid fields for styling and assistive technology. Templates render each
    field's errors with the id "<field id>-error" referenced here.

    Fields are marked after the form's own validation and also whenever an error is added
    later with add_error() (for example, a service refusing a duplicate name)."""

    def _post_clean(self):
        super()._post_clean()
        self._mark_invalid_fields()

    def add_error(self, field, error):
        super().add_error(field, error)
        self._mark_invalid_fields()

    def _mark_invalid_fields(self):
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                classes = attrs.get("class", "").split()
                if "is-invalid" not in classes:
                    attrs["class"] = " ".join([*classes, "is-invalid"])
                attrs["aria-invalid"] = "true"
                # Keep Django's help-text reference (<id>_helptext) alongside the error.
                described_by = [f"{self[name].id_for_label}-error"]
                if self.fields[name].help_text:
                    described_by.append(f"{self[name].id_for_label}_helptext")
                attrs["aria-describedby"] = " ".join(described_by)


class StudentRegistrationForm(AccessibleErrorsMixin, forms.Form):
    """DEC-201: full name, batch, semester and section. No department or shift field."""

    full_name = forms.CharField(
        max_length=150,
        strip=True,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
    )
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.active(),
        empty_label="Choose your batch",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.active(),
        empty_label="Choose your semester",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.active(),
        empty_label="Choose your section",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
