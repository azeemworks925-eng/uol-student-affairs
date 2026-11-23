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
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import batch_advisor_required, student_required, super_admin_required
from complaints.workspace import advisor_cohorts, cohort_value
from dsa.sorting import merge_sort

from . import services
from .forms import AnswerForm, FilterForm, SubmissionForm
from .models import Submission
from .permissions import get_visible_submission, visible_submissions
from .presentation import add_tones, sort_submissions

STUDENT_PAGE_SIZE = 10
STAFF_PAGE_SIZE = 20
LIST_PARAMS = ("type", "cohort", "status", "sort", "page")
FILTER_PARAMS = ("type", "cohort", "status", "sort")
ADVISOR_URLS = {"list": "advisor_voice", "detail": "advisor_voice_detail",
                "answer": "advisor_voice_answer", "review": "advisor_voice_review"}
SUPER_ADMIN_URLS = {"list": "super_admin_voice", "detail": "super_admin_voice_detail"}


# --- Student ---------------------------------------------------------------------------------

@student_required
@require_http_methods(["GET", "POST"])
def student_voice(request):
    form = SubmissionForm(request.POST if request.method == "POST" else None)
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
    own = sort_submissions(list(visible_submissions(request.user)))
    page = Paginator(own, STUDENT_PAGE_SIZE).get_page(request.GET.get("page"))
    add_tones(page.object_list)
    return render(request, "voice/student.html", {"form": form, "page": page, "total": len(own)},
                  status=400 if form.is_bound else 200)


@student_required
def student_voice_detail(request, pk):
    submission = get_visible_submission(request.user, pk)
    add_tones([submission])
    return render(request, "voice/student_detail.html", {"submission": submission})


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


def _filtered(visible, filters):
    submissions = visible
    if filters.value("type"):
        submissions = submissions.filter(type=filters.value("type"))
    if filters.value("status"):
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
    rows = sort_submissions(list(_filtered(visible, filters)), filters.value("sort"))
    page = Paginator(rows, STAFF_PAGE_SIZE).get_page(request.GET.get("page"))
    add_tones(page.object_list)
    state = _list_state(request)
    urls = SUPER_ADMIN_URLS if read_only else ADVISOR_URLS
    context = {
        "read_only": read_only,
        "urls": urls,
        "filters": filters,
        "page": page,
        "headline": _headline(visible),
        "has_cohorts": read_only or bool(cohorts),
        "has_filters": any(request.GET.get(name) for name in FILTER_PARAMS),
        "list_state": state,
        "page_state": _list_state(request, without=("page",)),
    }
    if pk is not None:
        submission = get_visible_submission(user, pk)
        add_tones([submission])
        context.update({
            "submission": submission,
            "cohort_label": _cohort_label(submission),
            "sap_id": submission.student.student_profile.sap_id,
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
