"""
Academic Structure for the Super Admin (DEC-330): batches, semesters, sections and the DFS
department tree. A 404 for other roles. Changes go through academics.services; nothing is deleted.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import StudentProfile
from accounts.people_views import apply_service_error
from accounts.permissions import super_admin_or_404

from . import services
from .forms import NamedEntryForm, SemesterEntryForm
from .models import Batch, Section, Semester
from .structure import cohort_counts, department_outline


@dataclass(frozen=True)
class Kind:
    key: str
    model: type
    title: str
    singular: str
    profile_field: str
    form_class: type
    label: str
    max_length: int | None
    help_text: str
    value_attr: str


KINDS = {
    "batch": Kind("batch", Batch, "Batches", "batch", "batch_id", NamedEntryForm, "Batch name", 50, "For example: Fall 2024.", "name"),
    "semester": Kind("semester", Semester, "Semesters", "semester", "semester_id", SemesterEntryForm, "Semester number", None, "", "number"),
    "section": Kind("section", Section, "Sections", "section", "section_id", NamedEntryForm, "Section name", 20, "For example: A.", "name"),
}


def _kind(key):
    if key not in KINDS:
        raise Http404
    return KINDS[key]


def _form(kind, *args, prefix_id, **kwargs):
    return kind.form_class(*args, label=kind.label, max_length=kind.max_length, help_text=kind.help_text,
                           auto_id=f"id_{kind.key}_{prefix_id}_%s", **kwargs)


def _page(request, *, bound=None, status=200):
    """`bound` is (kind key, entry pk or "new", form): that dialog reopens with its errors."""
    cards = []
    totals = {}
    for kind in KINDS.values():
        students = dict(StudentProfile.objects.order_by().values_list(kind.profile_field).annotate(total=Count("pk")))
        rows = []
        for entry in kind.model.objects.all():
            form = _form(kind, prefix_id=entry.pk, initial={"value": getattr(entry, kind.value_attr)})
            is_open = False
            if bound and bound[0] == kind.key and bound[1] == entry.pk:
                form, is_open = bound[2], True
            rows.append({"entry": entry, "students": students.get(entry.pk, 0), "form": form, "open": is_open,
                         "edit_id": f"dialog-edit-{kind.key}-{entry.pk}", "edit_title": f"edit-{kind.key}-{entry.pk}",
                         "active_id": f"dialog-active-{kind.key}-{entry.pk}", "active_title": f"active-{kind.key}-{entry.pk}"})
        add_form = _form(kind, prefix_id="new")
        add_open = False
        if bound and bound[0] == kind.key and bound[1] == "new":
            add_form, add_open = bound[2], True
        cards.append({"kind": kind, "rows": rows, "add_form": add_form, "add_open": add_open,
                      "add_id": f"dialog-add-{kind.key}", "add_title": f"add-{kind.key}"})
        totals[kind.key] = len(rows)
    active = {kind.key: set(kind.model.objects.active().values_list("pk", flat=True)) for kind in KINDS.values()}
    active_cohorts = sum(1 for b, s, c in cohort_counts()
                         if b in active["batch"] and s in active["semester"] and c in active["section"])
    root, cohort_total = department_outline()
    return render(request, "academics/structure.html", {
        "stats": [
            {"value": totals["batch"], "label": "Batches", "icon": "users"},
            {"value": totals["semester"], "label": "Semesters", "icon": "calendar"},
            {"value": totals["section"], "label": "Sections", "icon": "layers"},
            {"value": active_cohorts, "label": "Active cohorts", "icon": "check", "tone": "resolved"},
        ],
        "cards": cards,
        "tree": root,
        "cohort_total": cohort_total,
    }, status=status)


@super_admin_or_404
def structure(request):
    return _page(request)


@super_admin_or_404
@require_POST
def entry_add(request, kind):
    kind = _kind(kind)
    form = _form(kind, request.POST, prefix_id="new")
    if form.is_valid():
        try:
            entry = services.create_entry(kind.model, form.cleaned_data["value"])
        except ValidationError as error:
            _value_error(form, error)
        else:
            messages.success(request, f"{entry} was added.")
            return redirect("super_admin_structure")
    return _page(request, bound=(kind.key, "new", form), status=400)


@super_admin_or_404
@require_POST
def entry_edit(request, kind, pk):
    kind = _kind(kind)
    entry = get_object_or_404(kind.model, pk=pk)
    form = _form(kind, request.POST, prefix_id=pk)
    if form.is_valid():
        try:
            updated = services.update_entry(entry, form.cleaned_data["value"])
        except ValidationError as error:
            _value_error(form, error)
        else:
            messages.success(request, f"{updated} was saved.")
            return redirect("super_admin_structure")
    return _page(request, bound=(kind.key, pk, form), status=400)


def _value_error(form, error):
    """The model's name or number field is the form's one `value` field."""
    if hasattr(error, "error_dict"):
        for errors in error.error_dict.values():
            form.add_error("value", errors)
    else:
        apply_service_error(form, error)


@super_admin_or_404
@require_POST
def entry_active(request, kind, pk):
    kind = _kind(kind)
    entry = get_object_or_404(kind.model, pk=pk)
    wanted = request.POST.get("active") == "1"
    if wanted == entry.is_active:
        messages.info(request, f"{entry} is already {'active' if wanted else 'inactive'}.")
    else:
        services.set_entry_active(entry, wanted, actor=request.user)
        messages.success(request, f"{entry} was {'reactivated' if wanted else 'deactivated'}.")
    return redirect("super_admin_structure")
