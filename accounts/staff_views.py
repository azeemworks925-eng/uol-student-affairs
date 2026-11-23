"""
Staff pages for the Super Admin: Batch Advisors and Super Admins (DEC-330).

Every view is a 404 for other roles, and every change goes through accounts.services.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from academics.models import Batch, Section, Semester
from dsa.sorting import merge_sort

from . import people
from .models import AdvisorAssignment, User
from .people_forms import AccountActiveForm, AssignmentForm, NameForm, StaffCreateForm
from .people_views import PAGE_SIZE, apply_service_error, change_active, choice
from .permissions import super_admin_or_404
from .services import add_advisor_assignment, create_staff_account, remove_advisor_assignment, set_account_name

STAFF_KEYS = ("tab", "q", "status", "sort", "page")
ROLE_OF_TAB = {"advisors": User.Role.BATCH_ADVISOR, "admins": User.Role.SUPER_ADMIN}
LAST_ADMIN_NOTE = ("This is the last active Super Admin, so it can't be deactivated: nobody could manage the "
                   "portal. Add or reactivate another Super Admin first.")


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _cohort_labels(keys):
    batches = Batch.objects.in_bulk({key[0] for key in keys})
    semesters = Semester.objects.in_bulk({key[1] for key in keys})
    sections = Section.objects.in_bulk({key[2] for key in keys})
    ordered = merge_sort(list(keys), key=lambda k: (batches[k[0]].name, semesters[k[1]].number, sections[k[2]].name))
    return [f"{batches[k[0]]} · {semesters[k[1]]} · {sections[k[2]]}" for k in ordered]


def _assignment_labels(assignments):
    return ", ".join(f"{a.batch} · {a.semester} · {a.section}" for a in assignments)


# --- List ----------------------------------------------------------------------------------------

def _staff_page(request, tab, add_form=None, status=200):
    role = ROLE_OF_TAB[tab]
    rows = people.staff_rows(role)
    advisors = rows if tab == "advisors" else people.staff_rows(User.Role.BATCH_ADVISOR)
    covered, uncovered = people.coverage()
    current = {
        "q": " ".join(request.GET.get("q", "").split())[:60],
        "status": choice(request, "status", people.STAFF_STATUSES),
        "sort": choice(request, "sort", people.STAFF_SORTS),
    }
    shown = people.sort_staff(people.filter_staff(rows, query=current["q"], status=current["status"]), current["sort"])
    page = Paginator(shown, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "accounts/people/staff.html", {
        "tab": tab,
        "stats": [
            {"value": len(advisors), "label": "Batch Advisors", "icon": "users"},
            {"value": sum(1 for row in advisors if row.is_active), "label": "Active", "icon": "check", "tone": "resolved"},
            {"value": len(covered), "label": "Cohorts covered", "icon": "layers"},
            {"value": len(uncovered), "label": "Cohorts without an advisor", "icon": "inbox",
             "tone": "review" if uncovered else "accent"},
        ],
        "uncovered": _cohort_labels(uncovered),
        "page": page,
        "current": current,
        "statuses": people.STAFF_STATUSES,
        "sorts": people.STAFF_SORTS,
        "list_keys": STAFF_KEYS,
        "search_hidden": [("tab", tab)] + [(key, current[key]) for key in ("status", "sort") if current[key]],
        "has_filters": any(current.values()),
        "add_form": add_form or StaffCreateForm(initial={"role": role}),
        "open_add": add_form is not None or request.GET.get("new") == "1",
    }, status=status)


@super_admin_or_404
@require_http_methods(["GET", "POST"])
def staff(request):
    tab = request.GET.get("tab") if request.GET.get("tab") in ROLE_OF_TAB else "advisors"
    if request.method == "GET":
        return _staff_page(request, tab)
    tab = "admins" if request.POST.get("role") == User.Role.SUPER_ADMIN else "advisors"
    form = StaffCreateForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        try:
            user = create_staff_account(email=data["email"], full_name=data["full_name"], role=data["role"],
                                        actor=request.user, cohorts=form.cohort_values())
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, f"{user.get_full_name()} was added and can now sign in with Google.")
            return redirect("super_admin_staff_detail", user.pk)
    return _staff_page(request, tab, add_form=form, status=400)


# --- Detail --------------------------------------------------------------------------------------

def _member(pk):
    return get_object_or_404(User, pk=pk, role__in=User.STAFF_ROLES)


def _advisor(pk):
    return get_object_or_404(User, pk=pk, role=User.Role.BATCH_ADVISOR)


def _active_effect(request, user):
    """What the confirmation dialog says will happen."""
    if not user.is_active:
        if user.is_batch_advisor:
            return "They can sign in again with Google. Their cohort assignments are unchanged."
        return "They can sign in again with Google and manage the portal."
    if user.pk == request.user.pk:
        return "This is your own account. You will be signed out on your next request. Your history is kept."
    effect = "They are signed out on their next request and can't sign in until reactivated. Their history is kept."
    if user.is_batch_advisor:
        left = people.cohorts_left_uncovered(user)
        if left:
            effect += f" These cohorts would have no active advisor: {_assignment_labels(left)}."
        owned = people.owned_open_complaints(user)
        if owned:
            effect += f" They are the responsible owner of {_plural(owned, 'open complaint')}, which should be reassigned."
    return effect


def _is_last_active_admin(user):
    return user.is_super_admin and user.is_active and not User.objects.filter(
        role=User.Role.SUPER_ADMIN, is_active=True).exclude(pk=user.pk).exists()


def _detail(request, user, *, name_form=None, active_form=None, assignment_form=None, open_dialog="", status=200):
    assignments = people.advisor_assignments(user) if user.is_batch_advisor else []
    return render(request, "accounts/people/staff_detail.html", {
        "person": user,
        "assignments": assignments,
        "coverage": people.advisor_coverage(user, assignments) if user.is_batch_advisor else None,
        "activity": people.advisor_activity(user) if user.is_batch_advisor else [],
        "google_linked": people.google_linked(user),
        "name_form": name_form or NameForm(initial={"full_name": user.full_name}),
        "active_form": active_form or AccountActiveForm(user=user),
        "assignment_form": assignment_form or AssignmentForm(),
        "open_dialog": open_dialog,
        "active_open": open_dialog == "active",
        "active_effect": _active_effect(request, user),
        "active_blocked": LAST_ADMIN_NOTE if _is_last_active_admin(user) else "",
    }, status=status)


@super_admin_or_404
def staff_detail(request, pk):
    return _detail(request, _member(pk))


@super_admin_or_404
@require_POST
def staff_name(request, pk):
    user = _member(pk)
    form = NameForm(request.POST)
    if form.is_valid():
        try:
            set_account_name(user, form.cleaned_data["full_name"], actor=request.user)
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, "The name was updated.")
            return redirect("super_admin_staff_detail", pk)
    return _detail(request, _member(pk), name_form=form, open_dialog="name", status=400)


@super_admin_or_404
@require_POST
def staff_active(request, pk):
    user = _member(pk)
    left = people.cohorts_left_uncovered(user) if user.is_batch_advisor and user.is_active else []
    response = change_active(
        request, user,
        lambda form: _detail(request, _member(pk), active_form=form, open_dialog="active", status=400),
        "super_admin_staff_detail")
    if response is not None:
        return response
    if left:
        messages.warning(request, f"These cohorts now have no active advisor: {_assignment_labels(left)}.")
    return redirect("super_admin_staff_detail", pk)


@super_admin_or_404
@require_POST
def assignment_add(request, pk):
    user = _advisor(pk)
    form = AssignmentForm(request.POST)
    if form.is_valid():
        try:
            add_advisor_assignment(user, form.cohort(), actor=request.user)
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, "The cohort was assigned.")
            return redirect("super_admin_staff_detail", pk)
    return _detail(request, user, assignment_form=form, status=400)


@super_admin_or_404
@require_POST
def assignment_remove(request, pk, assignment_pk):
    user = _advisor(pk)
    assignment = (AdvisorAssignment.objects.filter(pk=assignment_pk, advisor=user)
                  .select_related("batch", "semester", "section").first())
    if assignment is None:
        messages.info(request, "This assignment was already removed.")
        return redirect("super_admin_staff_detail", pk)
    label = _assignment_labels([assignment])
    owned = people.owned_open_complaints(user, assignment)
    try:
        uncovered = remove_advisor_assignment(assignment)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("super_admin_staff_detail", pk)
    messages.success(request, f"{label} was removed from {user.get_full_name()}.")
    if uncovered:
        messages.warning(request, f"{label} now has no active advisor. Assign another advisor so its students are covered.")
    if owned:
        messages.warning(request, f"{user.get_full_name()} is still the named owner of {_plural(owned, 'open complaint')} "
                                  f"in {label}. Reassign from the complaint page.")
    return redirect("super_admin_staff_detail", pk)
