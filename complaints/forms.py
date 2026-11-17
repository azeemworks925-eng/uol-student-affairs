"""
Student complaint forms (Complaints Part 2).

Forms collect and check input only. They never take the student or the cohort (those come
from the signed-in account in complaints.services) and never write records: every change
goes through complaints.services.
"""

from django import forms

from accounts.forms import AccessibleErrorsMixin

from .models import TEXT_LIMIT, Complaint, ComplaintCategory, ComplaintSubcategory
from .services import NOTE_REQUIRED, STAFF_TRANSITIONS, eligible_advisors

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


# ---------- Batch Advisor workspace (Complaints Part 3) ----------

STATUS_NOTE_LABELS = {
    Complaint.Status.UNDER_REVIEW: "Note to the student",
    Complaint.Status.RESOLVED: "Resolution note",
    Complaint.Status.REJECTED: "Reason for rejection",
}


class AdvisorResponseForm(AccessibleErrorsMixin, forms.Form):
    message = forms.CharField(
        label="Response to the student",
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(5),
        help_text="Visible to the student. Sending a response does not change the status.",
        error_messages={"required": "Write a response."},
    )


class StatusUpdateForm(AccessibleErrorsMixin, forms.Form):
    """Offers only the transitions the service allows from the current status (DEC-221).

    `expected_status` carries the status the advisor saw, so a change based on a stale page
    is refused by services.change_status (P3-6).
    """

    new_status = forms.ChoiceField(
        label="New status",
        widget=forms.RadioSelect(attrs={"class": "form-check-input", "data-status-choice": ""}),
        error_messages={"required": "Choose the new status.", "invalid_choice": "Choose one of the statuses offered."},
    )
    note = forms.CharField(
        # Without JavaScript the label states the rule; with it, the label follows the choice.
        label="Note to the student (required for Resolved and Rejected)",
        required=False,
        max_length=TEXT_LIMIT,
        strip=True,
        widget=_textarea(4),
        help_text="Visible to the student in the complaint's history.",
    )
    expected_status = forms.ChoiceField(choices=Complaint.Status.choices, widget=forms.HiddenInput)

    def __init__(self, *args, complaint, seen_status=None, **kwargs):
        # Offer the transitions from the status the advisor saw (posted as expected_status),
        # so a stale page reaches services.change_status, which refuses it atomically with a
        # clear message, rather than failing here as an unexplained invalid choice.
        basis = seen_status if seen_status in Complaint.Status.values else complaint.status
        kwargs.setdefault("initial", {}).setdefault("expected_status", basis)
        super().__init__(*args, **kwargs)
        allowed = STAFF_TRANSITIONS.get(basis, set())
        self.fields["new_status"].choices = [(value, label) for value, label in Complaint.Status.choices if value in allowed]
        self.note_labels = {
            value: {"label": STATUS_NOTE_LABELS[value], "required": value in NOTE_REQUIRED} for value in allowed
        }

    def clean(self):
        cleaned = super().clean()
        new_status = cleaned.get("new_status")
        if new_status in NOTE_REQUIRED and not cleaned.get("note"):
            self.add_error("note", NOTE_REQUIRED[new_status])
        return cleaned


class ComplaintListFilterForm(forms.Form):
    """The workspace list's search, filters and sort (GET). Invalid values are ignored, so a
    filter can only ever narrow the user's visible complaints (DEC-205).

    Batch Advisors (Part 3) get an extra "Open" status. The Super Admin (Part 4 Stage 1)
    gets the spec's exact status list and an owner filter (pass `owners`)."""

    SORTS = [("activity", "Latest activity"), ("newest", "Newest submitted")]
    OPEN = "open"
    UNASSIGNED = "unassigned"

    q = forms.CharField(label="Search", required=False, max_length=100, strip=True, widget=forms.SearchInput)
    cohort = forms.ChoiceField(label="Cohort", required=False)
    status = forms.ChoiceField(label="Status", required=False)
    category = forms.ChoiceField(label="Category", required=False)
    sort = forms.ChoiceField(label="Sort by", required=False, choices=SORTS)

    def __init__(self, data, *, cohorts, categories, owners=None, include_open=True, all_cohorts_label="All assigned cohorts"):
        super().__init__(data)
        self.fields["cohort"].choices = [("", all_cohorts_label)] + cohorts
        self.fields["status"].choices = (
            [("", "All")] + ([(self.OPEN, "Open")] if include_open else []) + list(Complaint.Status.choices)
        )
        if owners is not None:
            # Current owners (eligible advisors or Super Admins who took over) and Unassigned.
            self.fields["owner"] = forms.ChoiceField(
                label="Responsible owner", required=False,
                choices=[("", "Any owner"), (self.UNASSIGNED, "Unassigned")]
                + [(str(user.pk), f"{user.get_full_name()} ({user.get_role_display()})") for user in owners],
            )
        # Staff filters mark inactive categories (Part 4 Stage 2); students never see this label.
        self.fields["category"].choices = [("", "All categories")] + [
            (str(c.pk), c.name if c.is_active else f"{c.name} (inactive)") for c in categories
        ]
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control" if name == "q" else "form-select")
        self.fields["q"].widget.attrs.update({"placeholder": "Search complaints", "aria-describedby": "ws-search-hint"})

    def value(self, name):
        """The cleaned value, or empty if the field was missing or invalid."""
        if not hasattr(self, "cleaned_data"):
            self.is_valid()
        return self.cleaned_data.get(name) or ""


class ResponsibleOwnerForm(AccessibleErrorsMixin, forms.Form):
    """Super Admin assigns, reassigns or takes over (DEC-310). Choices: active Batch Advisors
    of the exact cohort, and taking it over yourself. services.assign_responsible re-checks."""

    owner = forms.ChoiceField(
        label="Responsible owner",
        error_messages={"required": "Choose the responsible owner.", "invalid_choice": "Choose one of the people offered."},
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, complaint, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.people = {str(user.pk): user for user in eligible_advisors(complaint)}
        choices = [("", "Choose a person")] + [
            (pk, f"{user.get_full_name()} (Batch Advisor)") for pk, user in self.people.items()
        ]
        self.people[str(actor.pk)] = actor
        choices.append((str(actor.pk), f"Take it over yourself ({actor.get_full_name()})"))
        self.fields["owner"].choices = choices

    def clean_owner(self):
        return self.people[self.cleaned_data["owner"]]


# ---------- Category management (Part 4 Stage 2) ----------

class _NameForm(AccessibleErrorsMixin, forms.Form):
    """A name only. Normalisation, the 80-character limit and duplicates are decided by
    complaints.category_services; the form caps raw input and keeps the value on errors.
    There is no position or parent field: order changes by Up/Down, and parents are fixed."""

    name = forms.CharField(
        max_length=200,
        strip=True,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        error_messages={"required": "Enter a name."},
    )


class CategoryNameForm(_NameForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Category name"


class SubcategoryNameForm(_NameForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Subcategory name"


class ActiveStateForm(forms.Form):
    active = forms.TypedChoiceField(choices=[("1", "Activate"), ("0", "Deactivate")], coerce=lambda v: v == "1")


class MoveForm(forms.Form):
    direction = forms.ChoiceField(choices=[("up", "Move up"), ("down", "Move down")])
