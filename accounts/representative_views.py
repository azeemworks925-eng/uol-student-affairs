"""
Representatives (Batch Advisor) and CR/GR Management (Super Admin): Collective Issues CI-1.

Specification: docs/technical/COLLECTIVE_ISSUES_SPEC.md sections 5.5, 9.2 and 9.3. DEC-016,
DEC-245, DEC-323.

- A Batch Advisor sees and manages only the exact cohorts assigned to them (DEC-205); the
  Super Admin sees every known cohort. Anything else is a 404, never a hint that it exists.
- Every change is a POST (CSRF) to a cohort-scoped URL and goes through accounts.representation,
  which re-checks the actor, the cohort and every candidate under the cohort lock. Choices posted
  by the browser are only ever narrowed to the cohort's eligible students.
- There is no remove action: a post changes only by replacement or swap (DEC-323).
"""

from dataclasses import dataclass, field

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from academics.models import Batch, Section, Semester

from .forms import AccessibleErrorsMixin
from .models import AdvisorAssignment, CohortRepresentation, StudentProfile, User
from .permissions import batch_advisor_required, super_admin_required
from .representation import (
    POST_LABELS,
    POST_NAMES,
    Cohort,
    appoint_representatives,
    can_manage_cohort,
    current_holder_ids,
    eligible_candidates,
    replace_representatives,
    representation_breaches,
    swap_representatives,
)

COHORT_FIELDS = ("batch_id", "semester_id", "section_id")
STATUS_CHOICES = [("", "All cohorts"), ("awaiting", "Awaiting representatives"),
                  ("represented", "Represented"), ("inactive", "Inactive")]


@dataclass(frozen=True)
class Scope:
    name: str  # "advisor" or "admin"
    list_url_name: str
    appoint_url_name: str
    replace_url_name: str

    def cohorts(self, user):
        """The cohorts this user may see here, as Cohort values."""
        if self.name == "advisor":
            rows = AdvisorAssignment.objects.filter(advisor=user).values_list(*COHORT_FIELDS)
            return {Cohort(*row) for row in rows}
        rows = set(AdvisorAssignment.objects.values_list(*COHORT_FIELDS))
        rows |= set(StudentProfile.objects.values_list(*COHORT_FIELDS))
        rows |= set(CohortRepresentation.objects.values_list(*COHORT_FIELDS))
        return {Cohort(*row) for row in rows}


ADVISOR = Scope("advisor", "advisor_representatives", "advisor_representatives_appoint", "advisor_representatives_replace")
ADMIN = Scope("admin", "super_admin_representatives", "super_admin_representatives_appoint", "super_admin_representatives_replace")


# ---------------------------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------------------------

def _student_choices(students):
    return [("", "Choose a student")] + [
        (str(s.pk), f"{s.get_full_name()} ({s.student_profile.sap_id})") for s in students
    ]


class AppointForm(AccessibleErrorsMixin, forms.Form):
    cr = forms.ChoiceField(label="CR (Class Representative)")
    gr = forms.ChoiceField(label="GR (Girls Representative)")

    def __init__(self, *args, candidates=(), **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("cr", "gr"):
            self.fields[name].choices = _student_choices(candidates)
            self.fields[name].widget.attrs["class"] = "form-select"
        self.fields["cr"].error_messages["required"] = "Choose the CR."
        self.fields["gr"].error_messages["required"] = "Choose the GR."

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("cr") and cleaned.get("cr") == cleaned.get("gr"):
            self.add_error("gr", "The CR and the GR must be different students.")
        return cleaned


class ReplaceForm(AccessibleErrorsMixin, forms.Form):
    person = forms.ChoiceField()
    expected_period = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, post="cr", candidates=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].label = f"New {POST_LABELS[post]} ({POST_NAMES[post]})"
        self.fields["person"].choices = _student_choices(candidates)
        self.fields["person"].widget.attrs["class"] = "form-select"
        self.fields["person"].error_messages["required"] = f"Choose the new {POST_LABELS[post]}."


class SwapForm(forms.Form):
    expected_period = forms.IntegerField(widget=forms.HiddenInput)


# ---------------------------------------------------------------------------------------------
# Page data
# ---------------------------------------------------------------------------------------------

@dataclass
class CohortCard:
    cohort: Cohort
    label: str
    batch: Batch
    semester: Semester
    section: Section
    is_active: bool
    active_students: int
    period: CohortRepresentation | None
    history: list
    candidates: list
    forms: dict = field(default_factory=dict)
    open_form: str = ""

    @property
    def anchor(self):
        return "cohort-" + self.cohort.key.replace(".", "-")

    @property
    def state(self):
        if not self.is_active:
            return "inactive"
        return "represented" if self.period else "awaiting"

    @property
    def can_change(self):
        return self.is_active


def _cards(scope, user, cohorts):
    """Build every card with a fixed number of queries, whatever the number of cohorts."""
    if not cohorts:
        return []
    batches = Batch.objects.in_bulk({c.batch_id for c in cohorts})
    semesters = Semester.objects.in_bulk({c.semester_id for c in cohorts})
    sections = Section.objects.in_bulk({c.section_id for c in cohorts})
    students = (User.objects.filter(is_active=True, role=User.Role.STUDENT, student_profile__isnull=False,
                                    student_profile__batch_id__in={c.batch_id for c in cohorts})
                .select_related("student_profile").order_by("full_name", "email"))
    periods = list(CohortRepresentation.objects.filter(batch_id__in={c.batch_id for c in cohorts})
                   .select_related("cr__student_profile", "gr__student_profile", "ended_by", "started_by"))
    # Global, not just this page's cohorts: a student may hold a post in a cohort this page
    # doesn't show (another advisor's), and must not be offered as a candidate here.
    holders = current_holder_ids()
    members, history, current = {}, {}, {}
    for student in students:
        members.setdefault(Cohort.of(student.student_profile), []).append(student)
    for period in periods:
        cohort = Cohort.of(period)
        history.setdefault(cohort, []).append(period)
        if period.is_active:
            current[cohort] = period
    cards = []
    for cohort in cohorts:
        batch, semester, section = batches[cohort.batch_id], semesters[cohort.semester_id], sections[cohort.section_id]
        cohort_members = members.get(cohort, [])
        cards.append(CohortCard(
            cohort=cohort, label=f"{batch} · {semester} · {section}", batch=batch, semester=semester, section=section,
            is_active=batch.is_active and semester.is_active and section.is_active,
            active_students=len(cohort_members), period=current.get(cohort),
            history=sorted(history.get(cohort, []), key=lambda p: (p.started_at, p.pk), reverse=True),
            candidates=[s for s in cohort_members if s.pk not in holders],
        ))
    cards.sort(key=lambda c: (c.semester.number, c.batch.name, c.section.name, c.cohort.key))
    for card in cards:
        _default_forms(card)
    return cards


def _default_forms(card):
    if card.period:
        expected = {"expected_period": card.period.pk}
        card.forms.setdefault("cr", ReplaceForm(post="cr", candidates=card.candidates, initial=expected, prefix=f"{card.anchor}-cr"))
        card.forms.setdefault("gr", ReplaceForm(post="gr", candidates=card.candidates, initial=expected, prefix=f"{card.anchor}-gr"))
        card.forms.setdefault("swap", SwapForm(initial=expected, prefix=f"{card.anchor}-swap"))
    else:
        card.forms.setdefault("appoint", AppointForm(candidates=card.candidates, prefix=f"{card.anchor}-appoint"))


class FilterForm(forms.Form):
    status = forms.ChoiceField(label="Show", required=False, choices=STATUS_CHOICES)
    batch = forms.ModelChoiceField(label="Batch", required=False, queryset=Batch.objects.order_by("name"), empty_label="All batches")
    semester = forms.ModelChoiceField(label="Semester", required=False, queryset=Semester.objects.order_by("number"), empty_label="All semesters")
    section = forms.ModelChoiceField(label="Section", required=False, queryset=Section.objects.order_by("name"), empty_label="All sections")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-select"



def _render(request, scope, *, bound=None, status=200):
    cohorts = scope.cohorts(request.user)
    cards = _cards(scope, request.user, cohorts)
    if bound:
        key, action, form = bound
        for card in cards:
            if card.cohort.key == key:
                card.forms[action] = form
                card.open_form = action
    filters = FilterForm(request.GET or None) if scope.name == "admin" else None
    shown = cards
    if filters is not None and filters.is_valid():
        wanted = filters.cleaned_data
        shown = [c for c in cards
                 if (not wanted["status"] or c.state == wanted["status"])
                 and (not wanted["batch"] or c.batch.pk == wanted["batch"].pk)
                 and (not wanted["semester"] or c.semester.pk == wanted["semester"].pk)
                 and (not wanted["section"] or c.section.pk == wanted["section"].pk)]
    return render(request, "accounts/representatives/index.html", {
        "scope": scope,
        "cards": shown,
        "total": len(cards),
        "represented": sum(1 for c in cards if c.state == "represented"),
        "awaiting": sum(1 for c in cards if c.state == "awaiting"),
        "inactive": sum(1 for c in cards if c.state == "inactive"),
        "filters": filters,
        "filtered": filters is not None and any(request.GET.get(name) for name in ("status", "batch", "semester", "section")),
        "breaches": representation_breaches() if scope.name == "admin" else [],
    }, status=status)


# ---------------------------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------------------------

def _cohort_or_404(request, scope, key):
    cohort = Cohort.parse(key)
    if cohort is None or cohort not in scope.cohorts(request.user) or not can_manage_cohort(request.user, cohort):
        raise Http404
    return cohort


def _apply(request, scope, cohort, action, form, run, success):
    list_url = reverse(scope.list_url_name) + "#cohort-" + cohort.key.replace(".", "-")
    if form.is_valid():
        try:
            run(form.cleaned_data)
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                for name, errors in error.error_dict.items():
                    target = name if name in form.fields else ("person" if "person" in form.fields and name in ("cr", "gr") else None)
                    form.add_error(target, errors)
            else:
                form.add_error(None, error.messages)
            if isinstance(form, SwapForm):
                messages.error(request, " ".join(form.non_field_errors()) or "The CR and GR were not swapped.")
                return redirect(list_url)
            return _render(request, scope, bound=(cohort.key, action, form), status=400)
        except PermissionDenied:
            raise Http404
        messages.success(request, success(form.cleaned_data))
        return redirect(list_url)
    if isinstance(form, SwapForm):
        messages.error(request, "That change was not understood. Nothing was changed.")
        return redirect(list_url)
    return _render(request, scope, bound=(cohort.key, action, form), status=400)


def _candidates(cohort):
    return list(eligible_candidates(cohort))


def _student(pk):
    return User.objects.filter(pk=pk).first()


def _name(user):
    return user.get_full_name() if user else "The student"


def appoint(request, scope, key):
    cohort = _cohort_or_404(request, scope, key)
    prefix = "cohort-" + cohort.key.replace(".", "-") + "-appoint"
    form = AppointForm(request.POST, candidates=_candidates(cohort), prefix=prefix)

    def run(data):
        return appoint_representatives(request.user, cohort, cr=_student(data["cr"]), gr=_student(data["gr"]))

    return _apply(request, scope, cohort, "appoint", form, run, lambda d: (
        f"{_name(_student(d['cr']))} is now the CR and {_name(_student(d['gr']))} the GR."))


def replace(request, scope, key, post):
    cohort = _cohort_or_404(request, scope, key)
    prefix = "cohort-" + cohort.key.replace(".", "-") + f"-{post}"
    if post == "swap":
        form = SwapForm(request.POST, prefix=prefix)
        return _apply(request, scope, cohort, "swap", form,
                      lambda d: swap_representatives(request.user, cohort, expected_period=d["expected_period"]),
                      lambda d: "The CR and the GR have swapped posts.")
    if post not in ("cr", "gr"):
        raise Http404
    form = ReplaceForm(request.POST, post=post, candidates=_candidates(cohort), prefix=prefix)

    def run(data):
        person = _student(data["person"])
        kwargs = {post: person}
        return replace_representatives(request.user, cohort, expected_period=data["expected_period"], **kwargs)

    return _apply(request, scope, cohort, post, form, run, lambda d: (
        f"{_name(_student(d['person']))} is now the {POST_LABELS[post]}."))


# ---------------------------------------------------------------------------------------------
# Routed views
# ---------------------------------------------------------------------------------------------

@batch_advisor_required
def advisor_index(request):
    return _render(request, ADVISOR)


@batch_advisor_required
@require_POST
def advisor_appoint(request, cohort):
    return appoint(request, ADVISOR, cohort)


@batch_advisor_required
@require_POST
def advisor_replace(request, cohort, post):
    return replace(request, ADVISOR, cohort, post)


@super_admin_required
def admin_index(request):
    return _render(request, ADMIN)


@super_admin_required
@require_POST
def admin_appoint(request, cohort):
    return appoint(request, ADMIN, cohort)


@super_admin_required
@require_POST
def admin_replace(request, cohort, post):
    return replace(request, ADMIN, cohort, post)
