"""
Super Admin management of complaint categories and subcategories (Complaints Part 4 Stage 2).

Routes live under /super-admin/complaint-categories/ (not /super-admin/complaints/, whose
<reference>/ route would capture them). Every view is `super_admin_required`; every change is
POST + CSRF, goes through complaints.category_services (which re-checks the actor) and ends in
Post/Redirect/Get. Subcategories are looked up through their parent category, so a forged
category/subcategory pairing is a 404. There is no delete route.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import super_admin_required

from . import category_services as cs
from .forms import ActiveStateForm, CategoryNameForm, MoveForm, SubcategoryNameForm
from .models import ComplaintCategory, ComplaintSubcategory


def _category_or_404(pk):
    return get_object_or_404(ComplaintCategory, pk=pk)


def _subcategory_or_404(pk, sub_pk):
    return get_object_or_404(ComplaintSubcategory, pk=sub_pk, category_id=pk)


def _index_url():
    return reverse("super_admin_categories")


def _detail_url(category, anchor=""):
    return reverse("super_admin_category_detail", args=[category.pk]) + (f"#{anchor}" if anchor else "")


# ---------- Pages ----------

def _render_index(request, create_form=None, status=200):
    categories = ComplaintCategory.objects.annotate(
        subcategory_count=Count("subcategories", distinct=True),
        complaint_count=Count("complaints", distinct=True),
    ).order_by("position", "name", "pk")
    categories = list(categories)
    return render(request, "complaints/categories/index.html", {
        "categories": categories,
        "total": len(categories),
        "active_total": sum(1 for c in categories if c.is_active),
        "create_form": create_form or CategoryNameForm(prefix="new"),
    }, status=status)


def _render_detail(request, category, status=200, rename_form=None, sub_create_form=None, sub_forms=None):
    subcategories = list(
        category.subcategories.annotate(complaint_count=Count("complaints")).order_by("position", "name", "pk")
    )
    sub_forms = sub_forms or {}
    for sub in subcategories:
        sub.rename_form = sub_forms.get(sub.pk) or SubcategoryNameForm(prefix=f"sub-{sub.pk}", initial={"name": sub.name})
    return render(request, "complaints/categories/detail.html", {
        "category": category,
        "complaint_count": category.complaints.count(),
        "is_last_active": category.is_active and not ComplaintCategory.objects.active().exclude(pk=category.pk).exists(),
        "rename_form": rename_form or CategoryNameForm(prefix="category", initial={"name": category.name}),
        "subcategories": subcategories,
        "sub_create_form": sub_create_form or SubcategoryNameForm(prefix="new-sub"),
    }, status=status)


@super_admin_required
def index(request):
    return _render_index(request)


@super_admin_required
def detail(request, pk):
    return _render_detail(request, _category_or_404(pk))


# ---------- Changes ----------

def _apply(request, form, action, success_url, success_message, render_error):
    """Validate, run the service, then redirect. Field errors re-render the page (400);
    rule refusals (for example, the last active category) become a message."""
    if form.is_valid():
        try:
            action(form.cleaned_data)
        except ValidationError as error:
            if hasattr(error, "error_dict") and any(field in form.fields for field in error.error_dict):
                for field, field_errors in error.error_dict.items():
                    form.add_error(field if field in form.fields else None, field_errors)
                return render_error(form)
            messages.error(request, " ".join(error.messages))
            return redirect(success_url)
        messages.success(request, success_message)
        return redirect(success_url)
    if any(name in form.fields for name in ("name",)):
        return render_error(form)
    messages.error(request, "That change was not understood. Nothing was changed.")
    return redirect(success_url)


@super_admin_required
@require_POST
def category_create(request):
    form = CategoryNameForm(request.POST, prefix="new")
    return _apply(request, form, lambda d: cs.create_category(request.user, d["name"]),
                  _index_url(), "Category added. It is active and listed last.",
                  lambda f: _render_index(request, create_form=f, status=400))


@super_admin_required
@require_POST
def category_rename(request, pk):
    category = _category_or_404(pk)
    form = CategoryNameForm(request.POST, prefix="category")
    return _apply(request, form, lambda d: cs.rename_category(request.user, category, d["name"]),
                  _detail_url(category), "Category renamed. Existing complaints now show the new name.",
                  lambda f: _render_detail(request, category, status=400, rename_form=f))


@super_admin_required
@require_POST
def category_active(request, pk):
    category = _category_or_404(pk)
    form = ActiveStateForm(request.POST)
    wanted = form.is_valid() and form.cleaned_data["active"]
    return _apply(request, form, lambda d: cs.set_category_active(request.user, category, d["active"]),
                  _detail_url(category),
                  "Category activated." if wanted else "Category deactivated. Existing complaints keep it.",
                  lambda f: _render_detail(request, category, status=400))


@super_admin_required
@require_POST
def category_move(request, pk):
    category = _category_or_404(pk)
    return _apply(request, MoveForm(request.POST), lambda d: cs.move_category(request.user, category, d["direction"]),
                  _index_url() + f"#category-{category.pk}", "Order updated.",
                  lambda f: _render_index(request, status=400))


@super_admin_required
@require_POST
def subcategory_create(request, pk):
    category = _category_or_404(pk)
    form = SubcategoryNameForm(request.POST, prefix="new-sub")
    return _apply(request, form, lambda d: cs.create_subcategory(request.user, category, d["name"]),
                  _detail_url(category, "subcategories"), "Subcategory added.",
                  lambda f: _render_detail(request, category, status=400, sub_create_form=f))


@super_admin_required
@require_POST
def subcategory_rename(request, pk, sub_pk):
    sub = _subcategory_or_404(pk, sub_pk)
    form = SubcategoryNameForm(request.POST, prefix=f"sub-{sub.pk}")
    return _apply(request, form, lambda d: cs.rename_subcategory(request.user, sub, d["name"]),
                  _detail_url(sub.category, f"subcategory-{sub.pk}"),
                  "Subcategory renamed. Existing complaints now show the new name.",
                  lambda f: _render_detail(request, sub.category, status=400, sub_forms={sub.pk: f}))


@super_admin_required
@require_POST
def subcategory_active(request, pk, sub_pk):
    sub = _subcategory_or_404(pk, sub_pk)
    form = ActiveStateForm(request.POST)
    wanted = form.is_valid() and form.cleaned_data["active"]
    return _apply(request, form, lambda d: cs.set_subcategory_active(request.user, sub, d["active"]),
                  _detail_url(sub.category, f"subcategory-{sub.pk}"),
                  "Subcategory activated." if wanted else "Subcategory deactivated. Existing complaints keep it.",
                  lambda f: _render_detail(request, sub.category, status=400))


@super_admin_required
@require_POST
def subcategory_move(request, pk, sub_pk):
    sub = _subcategory_or_404(pk, sub_pk)
    return _apply(request, MoveForm(request.POST), lambda d: cs.move_subcategory(request.user, sub, d["direction"]),
                  _detail_url(sub.category, f"subcategory-{sub.pk}"), "Order updated.",
                  lambda f: _render_detail(request, sub.category, status=400))
