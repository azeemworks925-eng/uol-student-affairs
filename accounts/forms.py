from django import forms

from academics.models import Batch, Section, Semester


class StudentRegistrationForm(forms.Form):
    """DEC-201: full name, batch, semester and section. No department or shift field."""

    full_name = forms.CharField(max_length=150, strip=True)
    batch = forms.ModelChoiceField(queryset=Batch.objects.active())
    semester = forms.ModelChoiceField(queryset=Semester.objects.active())
    section = forms.ModelChoiceField(queryset=Section.objects.active())
