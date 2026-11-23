"""Section issue forms. They check input only: every change goes through issues.services."""

from django import forms
from django.core.exceptions import ValidationError

from accounts.forms import AccessibleErrorsMixin

from .models import DESCRIPTION_MAX, DESCRIPTION_MIN, RESPONSE_MAX, TITLE_MAX, TITLE_MIN
from .services import validate_content


class IssueForm(AccessibleErrorsMixin, forms.Form):
    title = forms.CharField(
        label="Title",
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": TITLE_MAX}),
        help_text=f"{TITLE_MIN} to {TITLE_MAX} characters.",
        error_messages={"required": "Write a title."},
    )
    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7}),
        help_text=f"{DESCRIPTION_MIN} to {DESCRIPTION_MAX} characters. Explain the problem for your whole section.",
        error_messages={"required": "Write a description."},
    )

    def clean(self):
        data = super().clean()
        if data.get("title") and data.get("description"):
            try:  # one rule, in one place: the service
                data["title"], data["description"] = validate_content(data["title"], data["description"])
            except ValidationError as error:
                for field, errors in error.error_dict.items():
                    self.add_error(field, errors)
        return data


class ResponseForm(AccessibleErrorsMixin, forms.Form):
    response = forms.CharField(
        label="Official response",
        max_length=RESPONSE_MAX,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        help_text="Only this section's current CR and GR will see it. The first response closes support.",
        error_messages={"required": "Write the response.", "max_length": f"Keep this to {RESPONSE_MAX} characters."},
    )


class ResolveForm(AccessibleErrorsMixin, forms.Form):
    note = forms.CharField(
        label="Resolution note",
        max_length=RESPONSE_MAX,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        help_text="Required. Only this section's current CR and GR will see it.",
        error_messages={"required": "Write the resolution note.", "max_length": f"Keep this to {RESPONSE_MAX} characters."},
    )
