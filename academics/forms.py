"""Forms for Academic Structure and Academic Terms. The services validate again (DEC-330)."""

from django import forms
from django.core.validators import MaxLengthValidator

from accounts.forms import AccessibleErrorsMixin


class NamedEntryForm(AccessibleErrorsMixin, forms.Form):
    value = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))

    def __init__(self, *args, label="Name", max_length=50, help_text="", **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["value"]
        field.label = label
        field.help_text = help_text
        field.validators.append(MaxLengthValidator(max_length))
        field.widget.attrs["maxlength"] = str(max_length)


class SemesterEntryForm(AccessibleErrorsMixin, forms.Form):
    value = forms.IntegerField(min_value=1, max_value=32767,
                               widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}))

    def __init__(self, *args, label="Semester number", max_length=None, help_text="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["value"].label = label
        self.fields["value"].help_text = help_text


class TermForm(AccessibleErrorsMixin, forms.Form):
    name = forms.CharField(max_length=50, help_text="For example: Fall 2026.",
                           widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))
    start_date = forms.DateField(label="First day", widget=forms.DateInput(
        format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}))
    end_date = forms.DateField(label="Last day", help_text="Included in the term.", widget=forms.DateInput(
        format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}))

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end <= start:
            self.add_error("end_date", "The last day must be after the first day.")
        return cleaned
