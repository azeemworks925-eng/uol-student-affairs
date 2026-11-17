from django import forms

from academics.models import Batch, Section, Semester


class AccessibleErrorsMixin:
    """Mark invalid fields for styling and assistive technology. Templates render each
    field's errors with the id "<field id>-error" referenced here."""

    def _post_clean(self):
        super()._post_clean()
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()
                attrs["aria-invalid"] = "true"
                attrs["aria-describedby"] = f"{self[name].id_for_label}-error"


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
