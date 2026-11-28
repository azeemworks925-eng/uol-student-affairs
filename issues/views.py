"""
Section issue pages. Views stay thin:
- the role decorator is on every view;
- records are loaded through issues.permissions, so anything not visible is a 404;
- changes go only through issues.services.

The Batch Advisor and Super Admin share one workspace. The Super Admin has no POST routes, so
that view is read-only by construction.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import batch_advisor_required, student_required, super_admin_required
from accounts.presentation import cohort_key, varies
from accounts.representation import can_act_as_representative, current_representative
from complaints.workspace import advisor_cohorts, cohort_value
from dsa.sorting import merge_sort

from . import services
from .forms import IssueForm, ResolveForm, ResponseForm
from .models import CollectiveIssue
from .permissions import get_visible_issue, is_cohort_student, is_current_representative_of, visible_issues
from .presentation import (
    SUPPORT_OPEN,
    add_display,
    issue_stats,
    newest_first,
    private_responses,
    status_journey,
    supported_ids,
)

Status = CollectiveIssue.Status
PAGE_SIZE = 20
LIST_PARAMS = ("q", "cohort", "status", "support", "page")
FILTER_PARAMS = ("q", "cohort", "status", "support")
SUPPORT_CHOICES = [("", "Any"), ("open", "Open"), ("closed", "Closed")]
STATUS_CHOICES = [("", "All"), *Status.choices]
ADVISOR_URLS = {"list": "advisor_issues", "detail": "advisor_issue_detail"}
SUPER_ADMIN_URLS = {"list": "super_admin_issues", "detail": "super_admin_issue_detail"}


def _detail_context(issue, *, show_private):
    add_display([issue])
    # Non-representative students never receive the status (DEC-243): their hero is tinted by
    # the support state instead. The supporter stack is anonymous: counts only (DEC-324).
    shown = min(issue.support_total, 3)
    context = {"issue": issue, "show_private": show_private,
               "hero_tone": issue.tone if show_private else issue.support_tone,
               "stack": range(shown), "stack_more": issue.support_total - shown}
    if show_private:
        context.update({"journey": status_journey(issue), "responses": private_responses(issue)})
    return context


# --- Students, CR and GR ---------------------------------------------------------------------

@student_required
def student_section_issues(request):
    """The current CR's and GR's page: the cohort's complete history. A 404 for anyone else."""
    period = current_representative(request.user)
    if period is None:
        raise Http404("No page found.")
    return _render_list(request, section=True)


@student_required
def student_issue_detail(request, reference):
    issue = get_visible_issue(request.user, reference)
    is_rep = is_current_representative_of(request.user, issue)
    context = _detail_context(issue, show_private=is_rep)
    context.update({
        "is_rep": is_rep,
        "can_support": issue.support_is_open and is_cohort_student(request.user, issue),
        "has_supported": issue.pk in supported_ids(request.user, [issue]),
        "back_url": reverse("student_section_issues" if is_rep else "student_home"),
        "crumb_label": "Section issues" if is_rep else "Home",
    })
    return render(request, "issues/detail.html", context)


@student_required
@require_POST
def student_issue_support(request, reference):
    issue = get_visible_issue(request.user, reference)
    try:
        recorded = services.support_issue(request.user, issue)
    except PermissionDenied:
        raise Http404("No issue found.") from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if recorded:
            messages.success(request, "Your support has been recorded.")
        else:
            messages.info(request, "You already support this issue.")
    if request.POST.get("from") == "home":
        return redirect("student_home")
    return redirect("student_issue_detail", reference=issue.reference)


@student_required
@require_http_methods(["GET", "POST"])
def student_issue_new(request):
    """Write → review → publish. Nothing is stored until the final, confirmed step."""
    period = can_act_as_representative(request.user)
    if period is None:
        raise Http404("No page found.")
    step = request.POST.get("step", "") if request.method == "POST" else ""
    if step == "edit":  # back from the review screen, keeping what was written
        form = IssueForm(initial={"title": request.POST.get("title", ""), "description": request.POST.get("description", "")})
        return render(request, "issues/new.html", {"form": form, "period": period})
    if step not in ("review", "publish"):
        return render(request, "issues/new.html", {"form": IssueForm(), "period": period})

    form = IssueForm(request.POST)
    if not form.is_valid():
        return render(request, "issues/new.html", {"form": form, "period": period}, status=400)
    title, description = form.cleaned_data["title"], form.cleaned_data["description"]
    confirm_error = ""
    if step == "publish":
        if request.POST.get("confirm") == "on":
            try:
                issue = services.publish_issue(request.user, title=title, description=description)
            except PermissionDenied:
                raise Http404("No page found.") from None
            except ValidationError as error:
                confirm_error = " ".join(error.messages)
            else:
                messages.success(request, f"Your issue was published. Its reference is {issue.reference}.")
                return redirect("student_issue_detail", reference=issue.reference)
        else:
            confirm_error = "Confirm that this issue can't be edited or removed."
    return render(request, "issues/review.html", {
        "title_text": title, "description_text": description, "period": period,
        "similar": services.similar_open_issues(period, title), "confirm_error": confirm_error,
    }, status=400 if confirm_error else 200)


# --- Staff workspace -------------------------------------------------------------------------

def _query(request):
    return " ".join(request.GET.get("q", "").split())[:100]


def _cohort_choices(user, visible):
    if user.is_batch_advisor:
        return advisor_cohorts(user)
    by_cohort = {cohort_value(i.batch_id, i.semester_id, i.section_id): i for i in visible}
    ordered = merge_sort(list(by_cohort.items()),
                         key=lambda pair: (pair[1].batch.name, pair[1].semester.number, pair[1].section.name))
    return [(value, f"{i.batch} · {i.semester} · {i.section}") for value, i in ordered]


def _clean_choice(value, choices):
    """A filter value only if it is one of the offered choices, so it can only narrow the list."""
    return value if value and value in [choice for choice, _label in choices] else ""


def _filtered(visible, *, cohort, status, support, query):
    issues = visible
    if cohort:
        batch_id, semester_id, section_id = (int(part) for part in cohort.split("."))
        issues = issues.filter(batch_id=batch_id, semester_id=semester_id, section_id=section_id)
    if status:
        issues = issues.filter(status=status)
    if support == "open":
        issues = issues.filter(SUPPORT_OPEN)
    elif support == "closed":
        issues = issues.exclude(SUPPORT_OPEN)
    if query:
        issues = issues.filter(Q(reference__icontains=query) | Q(title__icontains=query))
    return issues.order_by()  # merge-sorted in Python


def _list_state(request):
    return urlencode([(key, request.GET[key]) for key in LIST_PARAMS if request.GET.get(key)])


def _render_list(request, *, section=False):
    """The issues list: the CR's and GR's section page (`section`), or the staff Collective Issues
    page (Batch Advisor: their exact cohorts; Super Admin: the department, read-only)."""
    user = request.user
    read_only = user.is_super_admin
    visible = list(visible_issues(user).select_related("batch", "semester", "section").order_by())
    cohorts = [] if section else _cohort_choices(user, visible)
    cohort_filter = [("", "All cohorts" if read_only else "All assigned cohorts"), *cohorts]
    current = {
        "cohort": _clean_choice(request.GET.get("cohort", ""), cohorts),
        "status": _clean_choice(request.GET.get("status", ""), Status.choices),
        "support": _clean_choice(request.GET.get("support", ""), SUPPORT_CHOICES),
    }
    query = _query(request)
    # The stat cards count within every filter but the status and the support (Polish v2).
    stats_base = _filtered(visible_issues(user), query=query, cohort=current["cohort"], status="", support="")
    matches = _filtered(visible_issues(user), query=query, **current).select_related("raised_by", "semester", "section")
    rows = newest_first(matches)
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
    add_display(page.object_list, show_cohort=varies(page.object_list, cohort_key))
    state = _list_state(request)
    show_cohort_filter = len(cohorts) > 1 or (read_only and bool(cohorts))
    specs = [("q", "Search", None)] + ([("cohort", "Cohort", cohort_filter)] if show_cohort_filter else [])
    return render(request, "issues/section.html" if section else "issues/workspace.html", {
        "read_only": read_only, "urls": SUPER_ADMIN_URLS if read_only else ADVISOR_URLS, "page": page,
        "stats": issue_stats(stats_base), "query": query, "current": current,
        "cohort_choices": cohort_filter, "show_cohort_filter": show_cohort_filter,
        "status_tabs": STATUS_CHOICES, "support_choices": SUPPORT_CHOICES,
        "has_cohorts": section or read_only or bool(cohorts), "list_keys": LIST_PARAMS, "list_state": state,
        "query_suffix": f"?{state}" if state else "",
        "filter_specs": specs + [("support", "Support", SUPPORT_CHOICES)],
        "has_filters": any(request.GET.get(name) for name in FILTER_PARAMS),
        "can_raise": section and can_act_as_representative(user) is not None,
        "total": len(visible),
        "search_hidden": [(k, request.GET[k]) for k in ("cohort", "status", "support") if request.GET.get(k)],
    })


def _render_staff_detail(request, reference, *, response_form=None, resolve_form=None, status=200):
    user = request.user
    read_only = user.is_super_admin
    issue = get_visible_issue(user, reference)
    urls = SUPER_ADMIN_URLS if read_only else ADVISOR_URLS
    state = _list_state(request)
    context = _detail_context(issue, show_private=True)
    is_open = issue.status != Status.RESOLVED
    context.update({
        "read_only": read_only,
        "show_closed_at": True,
        "back_url": reverse(urls["list"]) + (f"?{state}" if state else ""),
        "crumb_label": "Collective Issues",
        "list_state": state,
        "can_review": not read_only and issue.status == Status.RECEIVED,
        "can_respond": not read_only and is_open,
        "can_resolve": not read_only and is_open,
        "response_form": response_form or ResponseForm(),
        "resolve_form": resolve_form or ResolveForm(),
    })
    return render(request, "issues/staff_detail.html", context, status=status)


@batch_advisor_required
def advisor_issues(request):
    return _render_list(request)


@batch_advisor_required
def advisor_issue_detail(request, reference):
    return _render_staff_detail(request, reference)


@super_admin_required
def super_admin_issues(request):
    return _render_list(request)


@super_admin_required
def super_admin_issue_detail(request, reference):
    return _render_staff_detail(request, reference)


def _after_action(request, reference):
    response = redirect("advisor_issue_detail", reference=reference)
    state = _list_state(request)
    if state:
        response["Location"] += f"?{state}"
    return response


def _expected_status(request):
    value = request.POST.get("expected_status", "")
    return value if value in Status.values else None


@batch_advisor_required
@require_POST
def advisor_issue_review(request, reference):
    issue = get_visible_issue(request.user, reference)
    try:
        services.mark_under_review(request.user, issue, expected_status=_expected_status(request))
    except PermissionDenied:
        raise Http404("No issue found.") from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Marked as Under Review. Support stays open.")
    return _after_action(request, reference)


@batch_advisor_required
@require_POST
def advisor_issue_respond(request, reference):
    issue = get_visible_issue(request.user, reference)
    form = ResponseForm(request.POST)
    if not form.is_valid():
        return _render_staff_detail(request, reference, response_form=form, status=400)
    try:
        services.send_response(request.user, issue, form.cleaned_data["response"])
    except PermissionDenied:
        raise Http404("No issue found.") from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Response sent. The current CR and GR have been notified.")
    return _after_action(request, reference)


@batch_advisor_required
@require_POST
def advisor_issue_resolve(request, reference):
    issue = get_visible_issue(request.user, reference)
    form = ResolveForm(request.POST)
    if not form.is_valid():
        return _render_staff_detail(request, reference, resolve_form=form, status=400)
    try:
        services.resolve(request.user, issue, form.cleaned_data["note"], expected_status=_expected_status(request))
    except PermissionDenied:
        raise Http404("No issue found.") from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Issue resolved. The current CR and GR have been notified.")
    return _after_action(request, reference)
