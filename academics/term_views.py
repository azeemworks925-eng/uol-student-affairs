"""
Academic Terms for the Super Admin (DEC-314, DEC-330). A 404 for other roles. Terms are never
deleted, and the current term changes only through academics.services, under its row locks.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.people_views import apply_service_error
from accounts.permissions import super_admin_or_404

from . import services
from .forms import TermForm
from .models import AcademicTerm


def _page(request, *, bound=None, status=200):
    """`bound` is (term pk or "new", form): that dialog reopens with its errors."""
    rows = []
    for term in AcademicTerm.objects.all():
        form = TermForm(auto_id=f"id_term_{term.pk}_%s",
                        initial={"name": term.name, "start_date": term.start_date, "end_date": term.end_date})
        is_open = False
        if bound and bound[0] == term.pk:
            form, is_open = bound[1], True
        rows.append({"term": term, "form": form, "open": is_open, "edit_id": f"dialog-edit-term-{term.pk}",
                     "edit_title": f"edit-term-{term.pk}", "current_id": f"dialog-current-term-{term.pk}",
                     "current_title": f"current-term-{term.pk}"})
    add_form = TermForm(auto_id="id_term_new_%s")
    add_open = False
    if bound and bound[0] == "new":
        add_form, add_open = bound[1], True
    return render(request, "academics/terms.html", {
        "rows": rows,
        "current": services.current_term(),
        "add_form": add_form,
        "add_open": add_open or request.GET.get("new") == "1",
    }, status=status)


def _term_values(form):
    data = form.cleaned_data
    return {"name": data["name"], "start_date": data["start_date"], "end_date": data["end_date"]}


@super_admin_or_404
def terms(request):
    return _page(request)


@super_admin_or_404
@require_POST
def term_add(request):
    form = TermForm(request.POST, auto_id="id_term_new_%s")
    if form.is_valid():
        try:
            term = services.create_term(**_term_values(form))
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, f"{term} was added. It is not the current term until you make it current.")
            return redirect("super_admin_terms")
    return _page(request, bound=("new", form), status=400)


@super_admin_or_404
@require_POST
def term_edit(request, pk):
    term = get_object_or_404(AcademicTerm, pk=pk)
    form = TermForm(request.POST, auto_id=f"id_term_{pk}_%s")
    if form.is_valid():
        try:
            updated = services.update_term(term, **_term_values(form))
        except ValidationError as error:
            apply_service_error(form, error)
        else:
            messages.success(request, f"{updated} was saved.")
            return redirect("super_admin_terms")
    return _page(request, bound=(pk, form), status=400)


@super_admin_or_404
@require_POST
def term_make_current(request, pk):
    term = get_object_or_404(AcademicTerm, pk=pk)
    try:
        previous, changed = services.set_current_term(term)
    except (services.CurrentTermConflict, AcademicTerm.DoesNotExist) as error:
        messages.error(request, f"No change was made. {error}")
        return redirect("super_admin_terms")
    if not changed:
        messages.info(request, f"{term} is already the current term.")
    elif previous:
        messages.success(request, f"{term} is now the current term (it replaces {previous}).")
    else:
        messages.success(request, f"{term} is now the current term.")
    return redirect("super_admin_terms")


@super_admin_or_404
@require_POST
def term_clear_current(request, pk):
    term = get_object_or_404(AcademicTerm, pk=pk)
    if not term.is_current:
        messages.info(request, f"{term} is not the current term, so nothing changed.")
        return redirect("super_admin_terms")
    try:
        services.clear_current_term(expected=term)
    except services.CurrentTermChanged as error:
        now = error.args[0] if error.args else None
        detail = f"{now} is now the current term." if now else "No term is current now."
        messages.error(request, f"No change was made: the current term changed at the same time. {detail}")
    except services.CurrentTermConflict as error:
        messages.error(request, f"No change was made. {error}")
    else:
        messages.success(request, f"{term} is no longer the current term. The Overview has no figures until one is set.")
    return redirect("super_admin_terms")
