"""Meeting forms. They check input only: every change goes through meetings.services."""

from django import forms
from django.utils import timezone

from accounts.forms import AccessibleErrorsMixin
from accounts.models import User
from accounts.permissions import visible_student_profiles

from .models import DURATIONS, LOCATION_MAX, NOTE_MAX, REASON_MAX, REASON_MESSAGE, REASON_MIN, Meeting
from .presentation import local_datetime
from .services import PAST_MESSAGE


def _date_field(label):
    return forms.DateField(
        label=label,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
        error_messages={"required": "Choose a date.", "invalid": "Enter a valid date."},
    )


def _time_field(label):
    return forms.TimeField(
        label=label,
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}, format="%H:%M"),
        error_messages={"required": "Choose a time.", "invalid": "Enter a valid time."},
    )


def _reason_field(label, help_text):
    return forms.CharField(
        label=label, min_length=REASON_MIN, max_length=REASON_MAX, strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text=help_text,
        error_messages={"required": "Write the reason for the meeting.", "min_length": REASON_MESSAGE,
                        "max_length": REASON_MESSAGE},
    )


class FutureTimeMixin:
    """Joins `date` and `time` (Asia/Karachi) into cleaned_data["starts_at"], which must be in the future."""

    def clean(self):
        data = super().clean()
        if data.get("date") and data.get("time"):
            starts_at = local_datetime(data["date"], data["time"])
            if starts_at <= timezone.now():
                self.add_error("time", PAST_MESSAGE)
            else:
                data["starts_at"] = starts_at
        return data


class RequestForm(FutureTimeMixin, AccessibleErrorsMixin, forms.Form):
    reason = _reason_field("Why would you like to meet?",
                           f"{REASON_MIN} to {REASON_MAX} characters. Only you, your Batch Advisors and the Super Admin can read it.")
    date = _date_field("Preferred date")
    time = _time_field("Preferred time")


class SlotForm(FutureTimeMixin, AccessibleErrorsMixin, forms.Form):
    """Date, time, duration and location: used to confirm a meeting."""

    date = _date_field("Date")
    time = _time_field("Start time")
    duration = forms.TypedChoiceField(
        label="Duration", coerce=int, initial=30,
        choices=[(minutes, f"{minutes} minutes") for minutes in DURATIONS],
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Choose a duration.", "invalid_choice": "Choose 15, 30, 45 or 60 minutes."},
    )
    location = forms.CharField(
        label="Location", max_length=LOCATION_MAX, strip=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "For example, Room 204, CS Block"}),
        error_messages={"required": "Enter where the meeting will take place.",
                        "max_length": f"Keep the location to {LOCATION_MAX} characters."},
    )


class SuggestForm(SlotForm):
    note = forms.CharField(
        label="Note to the student", required=False, max_length=NOTE_MAX, strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        error_messages={"max_length": f"Keep the note to {NOTE_MAX} characters."},
    )


class ReasonForm(AccessibleErrorsMixin, forms.Form):
    """The required reason for declining or cancelling."""

    reason = forms.CharField(
        label="Reason", max_length=NOTE_MAX, strip=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        help_text="The student can read this.",
        error_messages={"required": "Give a reason.", "max_length": f"Keep this to {NOTE_MAX} characters."},
    )


class StudentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        profile = user.student_profile
        return f"{user.get_full_name()} · {profile.sap_id} · {profile.batch} · {profile.section}"


class ScheduleForm(SlotForm):
    """An advisor books a meeting. Only active students of their assigned cohorts can be chosen."""

    field_order = ["student", "reason", "date", "time", "duration", "location"]

    student = StudentChoiceField(
        label="Student", queryset=User.objects.none(), empty_label="Choose a student",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Choose a student.", "invalid_choice": "Choose a student from your cohorts."},
    )
    reason = _reason_field("Purpose of the meeting", f"{REASON_MIN} to {REASON_MAX} characters. The student can read this.")

    def __init__(self, *args, advisor, **kwargs):
        super().__init__(*args, **kwargs)
        profiles = visible_student_profiles(advisor).filter(user__is_active=True)
        self.fields["student"].queryset = (
            User.objects.filter(student_profile__in=profiles)
            .select_related("student_profile__batch", "student_profile__section")
            .order_by("full_name", "pk")
        )


class FilterForm(forms.Form):
    """Super Admin list filters (GET). An invalid value is ignored, so a filter can only narrow the list."""

    status = forms.ChoiceField(label="Status", required=False, choices=[("", "All statuses"), *Meeting.Status.choices])
    cohort = forms.ChoiceField(label="Cohort", required=False)

    def __init__(self, data, *, cohorts):
        super().__init__(data)
        self.fields["cohort"].choices = [("", "All cohorts"), *cohorts]
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select"

    def value(self, name):
        if not hasattr(self, "cleaned_data"):
            self.is_valid()
        return self.cleaned_data.get(name) or ""
