"""
Student complaint forms (Complaints Part 2).

Forms collect and check input only. They never take the student or the cohort (those come
from the signed-in account in complaints.services) and never write records: every change
goes through complaints.services.
"""

from django import forms

from accounts.forms import AccessibleErrorsMixin

from .models import TEXT_LIMIT, Complaint, ComplaintCategory, ComplaintSubcategory

TITLE_LIMIT = Complaint._meta.get_field("title").max_length


def _textarea(rows, placeholder=""):
    return forms.Textarea(attrs={"class": "form-control", "rows": rows, "maxlength": TEXT_LIMIT, "placeholder": placeholder})


class ComplaintSubmissionForm(AccessibleErrorsMixin, forms.Form):
    category = forms.ModelChoiceField(
        queryset=ComplaintCategory.objects.none(),
        empty_label="Choose a category",
        widget=forms.Select(attrs={"class": "form-select", "data-complaint-category": ""}),
        error_messages={"required": "Choose a category.", "invalid_choice": "Choose an available category."},
    )
    # Filled in __init__ with active subcategories of active categories, grouped by category,
    # so the list is still understandable without JavaScript.
    subcategory = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=None,
        widget=forms.Select(attrs={"class": "form-select", "data-complaint-subcategory": ""}),
        error_messages={"invalid_choice": "Choose an available subcategory."},
    )
    title = forms.CharField(
        max_length=TITLE_LIMIT,
        strip=True,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        help_text="A short summary, for example “Lab timetable clash on Tuesdays”.",
        error_messages={"required": "Give your complaint a short title."},
    )
    description = forms.CharField(
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(8),
        help_text="Describe what happened and what you would like to be done. You cannot edit this "
        "after submitting, but you can add further information later.",
        error_messages={"required": "Describe your complaint."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = ComplaintCategory.objects.active()
        self.fields["category"].queryset = categories
        subcategories = ComplaintSubcategory.objects.active().filter(category__in=categories).select_related("category")
        self._subcategories = {sub.pk: sub for sub in subcategories}
        groups = {}
        for sub in subcategories:
            groups.setdefault(sub.category.name, []).append((sub.pk, sub.name))
        self.fields["subcategory"].choices = [("", "No subcategory")] + list(groups.items())
        self.has_subcategories = bool(groups)

    def clean_subcategory(self):
        pk = self.cleaned_data.get("subcategory")
        return self._subcategories.get(pk) if pk is not None else None

    def clean(self):
        cleaned = super().clean()
        category, subcategory = cleaned.get("category"), cleaned.get("subcategory")
        if category and subcategory and subcategory.category_id != category.pk:
            self.add_error("subcategory", "This subcategory belongs to a different category.")
        return cleaned


class FurtherInformationForm(AccessibleErrorsMixin, forms.Form):
    message = forms.CharField(
        label="Further information",
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(4),
        error_messages={"required": "Write the information you want to add."},
    )


class StillNotResolvedForm(AccessibleErrorsMixin, forms.Form):
    message = forms.CharField(
        label="What is still not resolved?",
        required=False,
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(3),
    )


class CancellationRequestForm(AccessibleErrorsMixin, forms.Form):
    reason = forms.CharField(
        label="Reason",
        required=False,
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(3),
    )
