"""Student Voice forms. They check input only: every change goes through voice.services."""

from django import forms

from accounts.forms import AccessibleErrorsMixin

from .models import LENGTH_MESSAGE, TEXT_MAX, TEXT_MIN, Submission


class SubmissionForm(AccessibleErrorsMixin, forms.Form):
    type = forms.ChoiceField(
        label="What would you like to share?",
        choices=Submission.Type.choices,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        error_messages={"required": "Choose Idea, Question or Feedback.", "invalid_choice": "Choose Idea, Question or Feedback."},
    )
    text = forms.CharField(
        label="Your message",
        min_length=TEXT_MIN,
        max_length=TEXT_MAX,
        strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        help_text=f"{TEXT_MIN} to {TEXT_MAX} characters. You cannot edit it after sending.",
        error_messages={"required": "Write your message.", "min_length": LENGTH_MESSAGE, "max_length": LENGTH_MESSAGE},
    )


class AnswerForm(AccessibleErrorsMixin, forms.Form):
    answer = forms.CharField(
        max_length=TEXT_MAX,
        strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        help_text="The student will see this and be notified. It cannot be changed after sending.",
        error_messages={"required": "Write your response.", "max_length": f"Keep your response to {TEXT_MAX} characters."},
    )

    def __init__(self, *args, submission, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["answer"].label = "Official answer" if submission.is_question else "Reply to the student"


class FilterForm(forms.Form):
    """List filters (GET). An invalid value is ignored, so a filter can only narrow the list."""

    SORTS = [("newest", "Newest first"), ("oldest", "Oldest first")]

    type = forms.ChoiceField(label="Type", required=False, choices=[("", "All types"), *Submission.Type.choices])
    cohort = forms.ChoiceField(label="Cohort", required=False)
    status = forms.ChoiceField(label="Status", required=False, choices=[("", "All statuses"), *Submission.Status.choices])
    sort = forms.ChoiceField(label="Sort by", required=False, choices=SORTS)

    def __init__(self, data, *, cohorts, all_cohorts_label):
        super().__init__(data)
        self.fields["cohort"].choices = [("", all_cohorts_label), *cohorts]
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select"

    def value(self, name):
        if not hasattr(self, "cleaned_data"):
            self.is_valid()
        return self.cleaned_data.get(name) or ""
