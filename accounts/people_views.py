"""
People pages for the Super Admin: Students and Staff (DEC-330).

Every view is a 404 for other roles. Views never save models: each change goes through
accounts.services, which holds the locks, the audit and the CR/GR rules. A refusal comes back as
a form error, and the dialog that caused it reopens.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from academics.models import Batch, Section, Semester

from . import people
from .models import StudentProfileChange, User
from .people_forms import AccountActiveForm, NameForm, StudentAccountForm, StudentEditForm
from .permissions import super_admin_or_404
from .services import create_student_account, set_account_active, set_account_name, update_student_details

PAGE_SIZE = 25
STUDENT_KEYS = ("q", "batch", "semester", "section", "status", "sort", "page")
CHANGE_KEYS = ("q", "field", "page")
FIELD_LABELS = {"full_name": "Full name", "batch": "Batch", "semester": "Semester", "section": "Section"}


def apply_service_error(form, error):
    """Put a service refusal on the matching field, or at the top of the form."""
    if hasattr(error, "error_dict"):
        for name, errors in error.error_dict.items():
            form.add_error(name if name in form.fields else None, errors)
    else:
        form.add_error(None, error.messages)


def choice(request, name, choices):
    value = request.GET.get(name, "")
    return value if value in [str(option) for option, _ in choices] else ""


def entry_choices(model, empty):
    return [("", empty)] + [(str(entry.pk), f"{entry} (inactive)" if not entry.is_active else str(entry))
                            for entry in model.objects.all()]


# --- Students: list ------------------------------------------------------------------------------

def _students_page(request, add_form=None, status=200):
    rows = people.student_rows()
    batches = entry_choices(Batch, "All batches")
    semesters = entry_choices(Semester, "All semesters")
    sections = entry_choices(Section, "All sections")
    current = {
        "q": " ".join(request.GET.get("q", "").split())[:60],
        "batch": choice(request, "batch", batches),
        "semester": choice(request, "semester", semesters),
        "section": choice(request, "section", sections),
        "status": choice(request, "status", people.STUDENT_STATUSES),
        "sort": choice(request, "sort", people.STUDENT_SORTS),
    }
    shown = people.search_students(rows, current["q"])
    shown = people.filter_students(shown, batch=current["batch"], semester=current["semester"],
                                   section=current["section"], status=current["status"])
    shown = people.sort_students(shown, current["sort"])
    page = Paginator(shown, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "accounts/people/students.html", {
        "stats": people.student_stats(rows),
        "page": page,
        "total": len(rows),
        "current": current,
        "batches": batches, "semesters": semesters, "sections": sections,
        "statuses": people.STUDENT_STATUSES, "sorts": people.STUDENT_SORTS,
        "list_keys": STUDENT_KEYS,
        "search_hidden": [(key, current[key]) for key in ("batch", "semester", "section", "status", "sort") if current[key]],
        "has_filters": any(current.values()),
        "add_form": add_form or StudentAccountForm(),
        "open_add": add_form is not None,
    }, status=status)


@super_admin_or_404
@require_http_methods(["GET", "POST"])
def students(request):
    if request.method == "GET":
        return _students_page(request)
    form = StudentAccountForm(request.POST)
    if form.is_valid():
        try:
            user = create_student_account(email=form.cleaned_data["email"], full_name=form.cleaned_data["full_name"])
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, f"{user.get_full_name()} can now sign in with Google and complete registration.")
            return redirect("super_admin_student_detail", user.pk)
    return _students_page(request, add_form=form, status=400)


@super_admin_or_404
def student_changes(request):
    """The whole audit trail of student profile changes, read-only (DEC-211)."""
    fields = [("", "All fields")] + list(FIELD_LABELS.items())
    current = {"q": " ".join(request.GET.get("q", "").split())[:60], "field": choice(request, "field", fields)}
    changes = StudentProfileChange.objects.select_related("profile__user", "changed_by")
    if current["field"]:
        changes = changes.filter(field_name=current["field"])
    if current["q"]:
        changes = changes.filter(Q(profile__sap_id__startswith=current["q"]) | Q(profile__user__email__icontains=current["q"])
                                 | Q(profile__user__full_name__icontains=current["q"]))
    page = Paginator(changes, PAGE_SIZE).get_page(request.GET.get("page"))
    for change in page:
        change.field_label = FIELD_LABELS.get(change.field_name, change.field_name)
    return render(request, "accounts/people/student_changes.html", {
        "page": page, "current": current, "fields": fields, "list_keys": CHANGE_KEYS,
        "search_hidden": [("field", current["field"])] if current["field"] else [],
        "has_filters": any(current.values()),
    })


# --- Students: detail ----------------------------------------------------------------------------

def _student(pk):
    return get_object_or_404(
        User.objects.select_related("student_profile__batch", "student_profile__semester", "student_profile__section"),
        pk=pk, role=User.Role.STUDENT)


def _student_detail(request, user, *, edit_form=None, active_form=None, open_dialog="", status=200):
    profile = getattr(user, "student_profile", None)
    sap_id = profile.sap_id if profile else (people.identity.extract_sap_id(user.email) or "")
    history = []
    if profile:
        history = list(profile.changes.select_related("changed_by")[:50])
        for change in history:
            change.field_label = FIELD_LABELS.get(change.field_name, change.field_name)
    if edit_form is None:
        edit_form = StudentEditForm(profile=profile) if profile else NameForm(initial={"full_name": user.full_name})
    activity = people.student_activity(user, sap_id)
    for item in activity:
        item["tile_label"] = f"{item['label']} · {item['detail']}"
    return render(request, "accounts/people/student_detail.html", {
        "person": user,
        "profile": profile,
        "sap_id": sap_id,
        "post": people.current_posts().get(user.pk, ""),
        "activity": activity,
        "history": history,
        "google_linked": people.google_linked(user),
        "edit_form": edit_form,
        "active_form": active_form or AccountActiveForm(user=user),
        "open_dialog": open_dialog,
        "active_open": open_dialog == "active",
    }, status=status)


@super_admin_or_404
def student_detail(request, pk):
    return _student_detail(request, _student(pk))


@super_admin_or_404
@require_POST
def student_edit(request, pk):
    user = _student(pk)
    profile = getattr(user, "student_profile", None)
    form = StudentEditForm(request.POST, profile=profile) if profile else NameForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        try:
            if profile:
                update_student_details(profile, full_name=data["full_name"], batch=data["batch"], semester=data["semester"],
                                       section=data["section"], actor=request.user,
                                       replacement=data.get("replacement") if form.moving else None)
            else:
                set_account_name(user, data["full_name"], actor=request.user)
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, "The student's details were updated.")
            return redirect("super_admin_student_detail", user.pk)
    return _student_detail(request, _student(pk), edit_form=form, open_dialog="edit", status=400)


def change_active(request, user, render_error, success_url):
    """Deactivate or reactivate through the lifecycle service. The posted intent guards against a
    stale page or a double click flipping the account back."""
    wanted = request.POST.get("active") == "1"
    if wanted == user.is_active:
        messages.info(request, f"{user.get_full_name()} is already {'active' if wanted else 'inactive'}.")
        return redirect(success_url, user.pk)
    form = AccountActiveForm(request.POST, user=user)
    if form.is_valid():
        try:
            set_account_active(user, wanted, actor=request.user, replacement=form.cleaned_data.get("replacement"))
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            state = "reactivated" if wanted else "deactivated"
            messages.success(request, f"{user.get_full_name()} was {state}.")
            return None
    return render_error(form)


@super_admin_or_404
@require_POST
def student_active(request, pk):
    user = _student(pk)
    response = change_active(request, user,
                             lambda form: _student_detail(request, _student(pk), active_form=form, open_dialog="active", status=400),
                             "super_admin_student_detail")
    return response or redirect("super_admin_student_detail", pk)
