"""
Student Voice pages. Views stay thin:
- the role decorator is on every view;
- records are loaded through voice.permissions, so anything not visible is a 404;
- changes go only through voice.services.

The Batch Advisor and Super Admin share one workspace page. The Super Admin's has no forms and
no POST routes, so it is read-only by construction.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import batch_advisor_required, student_required, super_admin_required
from accounts.presentation import cohort_key, varies
from complaints import ordering
from complaints.presentation import current_post
from complaints.workspace import advisor_cohorts, cohort_value
from dsa.sorting import merge_sort

from . import services
from .forms import AnswerForm, FilterForm, SubmissionForm
from .models import Submission
from .permissions import get_visible_submission, visible_submissions
from .presentation import list_display, sort_submissions, status_journey, timeline, voice_stats

STUDENT_PAGE_SIZE = 10
STAFF_PAGE_SIZE = 20
LIST_PARAMS = ("q", "type", "cohort", "status", "sort", "page")
FILTER_PARAMS = ("q", "type", "cohort", "status", "sort")
STUDENT_LIST_PARAMS = ("q", "type", "status", "sort", "page")
STATUS_TABS = [("", "All"), *Submission.Status.choices]
# The empty state's invitation tiles (Polish v2 "Student Voice"): each opens the form with its type.
TYPE_TILES = [
    {"type": Submission.Type.QUESTION, "label": "Ask a question", "icon": "voice"},
    {"type": Submission.Type.IDEA, "label": "Share an idea", "icon": "sparkle"},
    {"type": Submission.Type.FEEDBACK, "label": "Give feedback", "icon": "check"},
]
ADVISOR_URLS = {"list": "advisor_voice", "detail": "advisor_voice_detail",
                "answer": "advisor_voice_answer", "review": "advisor_voice_review"}
SUPER_ADMIN_URLS = {"list": "super_admin_voice", "detail": "super_admin_voice_detail"}


# --- Student ---------------------------------------------------------------------------------

@student_required
@require_http_methods(["GET", "POST"])
def student_voice(request):
    # The empty state's invitation tiles open the form with their type chosen (?new=1&type=…).
    chosen_type = request.GET.get("type", "") if request.GET.get("new") else ""
    initial = {"type": chosen_type} if chosen_type in Submission.Type.values else None
    form = SubmissionForm(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit(request.user, type=form.cleaned_data["type"], text=form.cleaned_data["text"])
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                for field, field_errors in error.error_dict.items():
                    form.add_error(field if field in form.fields else None, field_errors)
            else:
                form.add_error(None, error)
        else:
            messages.success(request, "Thank you. Your Batch Advisors can now see your message.")
            return redirect("student_voice")
    visible = visible_submissions(request.user)
    filters = FilterForm(request.GET, cohorts=[], all_cohorts_label="")
    query = _query(request)
    base = _filtered(visible, filters, with_status=False)
    if query:
        base = base.filter(text__icontains=query)
    rows = base.filter(status=filters.value("status")) if filters.value("status") else base
    own = sort_submissions(list(rows), filters.value("sort"))
    page = Paginator(own, STUDENT_PAGE_SIZE).get_page(request.GET.get("page"))
    list_display(page.object_list, show_cohort=varies(page.object_list, cohort_key))
    state = urlencode([(key, request.GET[key]) for key in STUDENT_LIST_PARAMS if request.GET.get(key)])
    return render(request, "voice/student.html", {
        "form": form, "page": page, "total": visible.count(), "filters": filters, "query": query,
        "current": {name: filters.value(name) for name in ("type", "status", "sort")},
        "has_filters": any(request.GET.get(name) for name in ("q", "type", "status", "sort")),
        "stats": voice_stats(base), "list_keys": STUDENT_LIST_PARAMS, "list_state": state,
        "query_suffix": f"?{state}" if state else "",
        "status_tabs": STATUS_TABS, "type_tiles": TYPE_TILES,
        "filter_specs": [("q", "Search", None), ("type", "Type", filters.fields["type"].choices),
                         ("sort", "Sort", filters.fields["sort"].choices)],
        "list_defaults": {"sort": "newest"},
        "search_hidden": [(k, request.GET[k]) for k in ("type", "status", "sort") if request.GET.get(k)],
        "open_new": form.is_bound or bool(request.GET.get("new")),
    }, status=400 if form.is_bound else 200)


@student_required
def student_voice_detail(request, pk):
    submission = get_visible_submission(request.user, pk)
    list_display([submission])
    state = urlencode([(key, request.GET[key]) for key in STUDENT_LIST_PARAMS if request.GET.get(key)])
    return render(request, "voice/student_detail.html", {
        "submission": submission, "list_state": state, "journey": status_journey(submission),
        "timeline": timeline(submission, staff=False),
    })


# --- Staff workspace -------------------------------------------------------------------------

def _cohort_label(submission):
    return f"{submission.batch} · {submission.semester} · {submission.section}"


def _submission_cohorts(visible):
    """(value, label) filter choices for the cohorts that have submissions, in academic order."""
    by_cohort = {cohort_value(s.batch_id, s.semester_id, s.section_id): s for s in visible.order_by()}
    ordered = merge_sort(
        list(by_cohort.items()),
        key=lambda pair: (pair[1].batch.name, pair[1].semester.number, pair[1].section.name),
    )
    return [(value, _cohort_label(submission)) for value, submission in ordered]


def _query(request):
    return " ".join(request.GET.get("q", "").split())[:100]


def _filtered(visible, filters, with_status=True):
    """The list's filters. Without the status, it is what the stat cards count (Polish v2)."""
    submissions = visible
    if filters.value("type"):
        submissions = submissions.filter(type=filters.value("type"))
    if with_status and filters.value("status"):
        submissions = submissions.filter(status=filters.value("status"))
    if filters.value("cohort"):  # validated against the offered choices
        batch_id, semester_id, section_id = (int(part) for part in filters.value("cohort").split("."))
        submissions = submissions.filter(batch_id=batch_id, semester_id=semester_id, section_id=section_id)
    return submissions.order_by()  # merge-sorted in Python


def _list_state(request, without=()):
    return urlencode([(key, request.GET[key]) for key in LIST_PARAMS if key not in without and request.GET.get(key)])


def _headline(visible):
    counts = dict(visible.order_by().values_list("status").annotate(n=Count("id")))
    if not counts:
        return "No submissions yet."
    waiting = counts.get(Submission.Status.WAITING, 0)
    if not waiting:
        return "Nothing is waiting."
    return f"{waiting} submission{'' if waiting == 1 else 's'} waiting."


def _render_workspace(request, pk=None, *, answer_form=None, status=200):
    user = request.user
    read_only = user.is_super_admin
    visible = visible_submissions(user)
    cohorts = _submission_cohorts(visible) if read_only else advisor_cohorts(user)
    filters = FilterForm(request.GET, cohorts=cohorts,
                         all_cohorts_label="All cohorts" if read_only else "All assigned cohorts")
    base = _filtered(visible, filters, with_status=False)
    query = _query(request)
    if query:  # students by name or SAP ID, from a trie of the visible submissions only
        base = base.filter(Q(student_id__in=ordering.matching_student_ids(visible, query)) | Q(text__icontains=query))
    matches = base.filter(status=filters.value("status")) if filters.value("status") else base
    rows = sort_submissions(list(matches.select_related("student", "semester", "section")), filters.value("sort"))
    page = Paginator(rows, STAFF_PAGE_SIZE).get_page(request.GET.get("page"))
    list_display(page.object_list, show_cohort=varies(page.object_list, cohort_key))
    state = _list_state(request)
    urls = SUPER_ADMIN_URLS if read_only else ADVISOR_URLS
    show_cohort_filter = len(cohorts) > 1
    context = {
        "read_only": read_only,
        "urls": urls,
        "filters": filters,
        "page": page,
        "headline": _headline(visible),
        "stats": voice_stats(base),
        "query": query,
        "query_suffix": f"?{state}" if state else "",
        "status_tabs": STATUS_TABS,
        "show_cohort_filter": show_cohort_filter,
        "filter_specs": [("q", "Search", None), ("type", "Type", filters.fields["type"].choices)]
        + ([("cohort", "Cohort", filters.fields["cohort"].choices)] if show_cohort_filter else [])
        + [("sort", "Sort", filters.fields["sort"].choices)],
        "list_defaults": {"sort": "newest"},
        "current": {name: filters.value(name) for name in ("type", "cohort", "status", "sort")},
        "list_keys": LIST_PARAMS,
        "search_hidden": [(k, request.GET[k]) for k in ("type", "cohort", "status", "sort") if request.GET.get(k)],
        "has_cohorts": read_only or bool(cohorts),
        "has_filters": any(request.GET.get(name) for name in FILTER_PARAMS),
        "list_state": state,
        "page_state": _list_state(request, without=("page",)),
    }
    if pk is not None:
        submission = get_visible_submission(user, pk)
        list_display([submission])
        context.update({
            "submission": submission,
            "journey": status_journey(submission),
            "timeline": timeline(submission, staff=True),
            "cohort_label": _cohort_label(submission),
            "sap_id": submission.student.student_profile.sap_id,
            "student_post": current_post(submission.student),
            "can_answer": not read_only and not submission.answer,
            "can_review": not read_only and not submission.is_question
            and submission.status == Submission.Status.WAITING,
            "answer_form": answer_form or AnswerForm(submission=submission),
        })
    return render(request, "voice/workspace.html", context, status=status)


def _detail_redirect(request, url_name, pk):
    response = redirect(url_name, pk=pk)
    state = _list_state(request)
    if state:
        response["Location"] += f"?{state}"
    return response


@batch_advisor_required
def advisor_voice(request, pk=None):
    return _render_workspace(request, pk)


@super_admin_required
def super_admin_voice(request, pk=None):
    return _render_workspace(request, pk)


@batch_advisor_required
@require_POST
def advisor_answer(request, pk):
    submission = get_visible_submission(request.user, pk)
    form = AnswerForm(request.POST, submission=submission)
    if not form.is_valid():
        return _render_workspace(request, pk, answer_form=form, status=400)
    try:
        services.answer(request.user, submission, form.cleaned_data["answer"])
    except ValidationError as error:  # for example, a colleague answered first
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Sent. The student has been notified.")
    return _detail_redirect(request, "advisor_voice_detail", pk)


@batch_advisor_required
@require_POST
def advisor_review(request, pk):
    submission = get_visible_submission(request.user, pk)
    try:
        services.mark_reviewed(request.user, submission)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Marked as reviewed.")
    return _detail_redirect(request, "advisor_voice_detail", pk)
