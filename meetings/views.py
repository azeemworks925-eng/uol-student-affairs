"""
Meeting pages. Views stay thin:
- the role decorator is on every view;
- records are loaded through meetings.permissions, so anything not visible is a 404;
- changes go only through meetings.services.

The Super Admin has one list and no POST routes, so that role is read-only by construction.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import batch_advisor_required, student_required, super_admin_required
from complaints.presentation import current_post
from complaints.workspace import advisor_cohorts, cohort_value
from dsa.sorting import merge_sort

from . import services
from .forms import FilterForm, ReasonForm, RequestForm, ScheduleForm, SlotForm, SuggestForm
from .models import Meeting
from .permissions import get_visible_meeting, visible_meetings
from .presentation import (build_month, build_week, decorate, group_by_day, latest_first, meeting_stats, overlap_token,
                           overlap_warnings, split_upcoming)

Status = Meeting.Status
ADMIN_PAGE_SIZE = 20
CLOSED_LIMIT = 20
# The List | Month | Week switcher for each role.
VIEW_URLS = {
    "student_meetings": {"list": "student_meetings", "month": "student_meetings_month", "week": "student_meetings_week"},
    "advisor_meetings": {"list": "advisor_meetings", "month": "advisor_meetings_month", "week": "advisor_meetings_week"},
    "super_admin_meetings": {"list": "super_admin_meetings", "month": "super_admin_meetings_month", "week": "super_admin_meetings_week"},
}


def _add_service_errors(form, error):
    if hasattr(error, "error_dict"):
        for field, field_errors in error.error_dict.items():
            form.add_error(field if field in form.fields else None, field_errors)
    else:
        form.add_error(None, error)


def _run(request, action, success):
    """Run a service call and report the outcome. A refused action (for example, a colleague
    acted first) shows its reason."""
    try:
        action()
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, success)


# --- Student ---------------------------------------------------------------------------------

@student_required
@require_http_methods(["GET", "POST"])
def student_meetings(request):
    form = RequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            services.request_meeting(request.user, reason=form.cleaned_data["reason"],
                                     preferred_at=form.cleaned_data["starts_at"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Request sent. Your Batch Advisors can now see it.")
            return redirect("student_meetings")
    own = decorate(list(visible_meetings(request.user).order_by()), request.user)
    upcoming, closed = split_upcoming(own)
    return render(request, "meetings/student.html", {
        "form": form,
        "groups": group_by_day(upcoming),
        "upcoming": upcoming,
        "closed": closed,
        "stats": meeting_stats(own),
        "view_urls": VIEW_URLS["student_meetings"],
        "open_new": form.is_bound or bool(request.GET.get("new")),
    }, status=400 if form.is_bound else 200)


def _student_detail(request, meeting, cancel_form=None, status=200):
    decorate([meeting], request.user)
    return render(request, "meetings/detail.html", {
        "meeting": meeting,
        "viewer_is_student": True,
        "list_url_name": "student_meetings",
        "cancel_form": cancel_form or ReasonForm(prefix="cancel"),
        "events": meeting.events.select_related("actor"),
    }, status=status)


@student_required
def student_meeting_detail(request, pk):
    return _student_detail(request, get_visible_meeting(request.user, pk))


@student_required
@require_POST
def student_accept(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    _run(request, lambda: services.accept_suggestion(request.user, meeting), "Accepted. Your meeting is confirmed.")
    return redirect("student_meeting_detail", pk=pk)


@student_required
@require_POST
def student_decline(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    _run(request, lambda: services.decline_suggestion(request.user, meeting), "You declined the suggested time.")
    return redirect("student_meeting_detail", pk=pk)


@student_required
@require_POST
def student_cancel(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    form = ReasonForm(request.POST, prefix="cancel")
    if not form.is_valid():
        return _student_detail(request, meeting, cancel_form=form, status=400)
    _run(request, lambda: services.cancel(request.user, meeting, form.cleaned_data["reason"]), "Meeting cancelled.")
    return redirect("student_meeting_detail", pk=pk)


@student_required
def student_month(request):
    return _render_month(request, "student_meetings", "student_meeting_detail")


@student_required
def student_week(request):
    return _render_week(request, "student_meetings", "student_meeting_detail")


# --- Month view (student and advisor) ----------------------------------------------------------

def _calendar_viewer(user):
    """Who a Google Calendar link is for. Read-only oversight has none."""
    return None if user.is_super_admin else user


def _render_month(request, list_url_name, detail_url_name):
    month = build_month(visible_meetings(request.user), request.GET.get("month"), request.GET.get("day"),
                        _calendar_viewer(request.user))
    return render(request, "meetings/month.html", {
        "month": month, "list_url_name": list_url_name, "detail_url_name": detail_url_name,
        "view_urls": VIEW_URLS[list_url_name], "show_student": not request.user.is_student,
    })


def _render_week(request, list_url_name, detail_url_name):
    week = build_week(visible_meetings(request.user), request.GET.get("week"), request.GET.get("day"),
                      _calendar_viewer(request.user))
    return render(request, "meetings/week.html", {
        "week": week, "list_url_name": list_url_name, "detail_url_name": detail_url_name,
        "view_urls": VIEW_URLS[list_url_name], "show_student": not request.user.is_student,
    })


# --- Batch Advisor ---------------------------------------------------------------------------

def _prefilled_slot(meeting):
    when = timezone.localtime(meeting.preferred_at) if meeting.preferred_at else None
    return {"date": when.date(), "time": when.time().replace(second=0, microsecond=0)} if when else {}


def _advisor_detail(request, meeting, *, confirm_form=None, suggest_form=None, decline_form=None, cancel_form=None,
                    warnings=(), token="", status=200):
    decorate([meeting], request.user)
    initial = _prefilled_slot(meeting)
    return render(request, "meetings/detail.html", {
        "meeting": meeting,
        "viewer_is_advisor": True,
        "student_post": current_post(meeting.student),
        "list_url_name": "advisor_meetings",
        "confirm_form": confirm_form or SlotForm(prefix="confirm", initial=initial),
        "suggest_form": suggest_form or SuggestForm(prefix="suggest", initial=initial),
        "decline_form": decline_form or ReasonForm(prefix="decline"),
        "cancel_form": cancel_form or ReasonForm(prefix="cancel"),
        "open_confirm": bool(confirm_form),
        "open_suggest": bool(suggest_form),
        "open_decline": bool(decline_form),
        "overlap_warnings": warnings,
        "overlap_token": token,
        "events": meeting.events.select_related("actor"),
    }, status=status)


def _unacknowledged_overlap(request, starts_at, duration, exclude_pk=None):
    """The overlap warning and its token, unless the advisor already accepted this exact time."""
    warnings = overlap_warnings(request.user, starts_at, duration, exclude_pk)
    token = overlap_token(starts_at, duration)
    if not warnings or request.POST.get("overlap_ack") == token:
        return [], ""
    return warnings, token


@batch_advisor_required
def advisor_meetings(request):
    meetings = decorate(list(visible_meetings(request.user).order_by()), request.user)
    upcoming, closed = split_upcoming(meetings)
    needs_decision = [m for m in upcoming if m.is_requested]
    return render(request, "meetings/advisor.html", {
        "needs_decision": needs_decision,
        "waiting_for_student": [m for m in upcoming if m.is_time_suggested],
        "groups": group_by_day([m for m in upcoming if m.is_confirmed]),
        "closed": closed[:CLOSED_LIMIT],
        "confirmed": [m for m in upcoming if m.is_confirmed],
        "stats": meeting_stats(meetings),
        "view_urls": VIEW_URLS["advisor_meetings"],
        "has_cohorts": bool(advisor_cohorts(request.user)),
    })


@batch_advisor_required
def advisor_meeting_detail(request, pk):
    return _advisor_detail(request, get_visible_meeting(request.user, pk))


@batch_advisor_required
@require_POST
def advisor_confirm(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    form = SlotForm(request.POST, prefix="confirm")
    if not form.is_valid():
        return _advisor_detail(request, meeting, confirm_form=form, status=400)
    data = form.cleaned_data
    if meeting.is_requested:
        warnings, token = _unacknowledged_overlap(request, data["starts_at"], data["duration"], meeting.pk)
        if warnings:  # a warning, not a block: the advisor can confirm anyway
            return _advisor_detail(request, meeting, confirm_form=form, warnings=warnings, token=token)
    _run(request, lambda: services.confirm(request.user, meeting, starts_at=data["starts_at"],
                                           duration=data["duration"], location=data["location"]),
         "Meeting confirmed. The student has been notified.")
    return redirect("advisor_meeting_detail", pk=pk)


@batch_advisor_required
@require_POST
def advisor_suggest(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    form = SuggestForm(request.POST, prefix="suggest")
    if not form.is_valid():
        return _advisor_detail(request, meeting, suggest_form=form, status=400)
    data = form.cleaned_data
    _run(request, lambda: services.suggest(request.user, meeting, starts_at=data["starts_at"], duration=data["duration"],
                                           location=data["location"], note=data["note"]),
         "Time suggested. The student has been notified.")
    return redirect("advisor_meeting_detail", pk=pk)


@batch_advisor_required
@require_POST
def advisor_decline(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    form = ReasonForm(request.POST, prefix="decline")
    if not form.is_valid():
        return _advisor_detail(request, meeting, decline_form=form, status=400)
    _run(request, lambda: services.decline(request.user, meeting, form.cleaned_data["reason"]),
         "Request declined. The student has been notified.")
    return redirect("advisor_meeting_detail", pk=pk)


@batch_advisor_required
@require_POST
def advisor_cancel(request, pk):
    meeting = get_visible_meeting(request.user, pk)
    form = ReasonForm(request.POST, prefix="cancel")
    if not form.is_valid():
        return _advisor_detail(request, meeting, cancel_form=form, status=400)
    _run(request, lambda: services.cancel(request.user, meeting, form.cleaned_data["reason"]),
         "Meeting cancelled. The student has been notified.")
    return redirect("advisor_meeting_detail", pk=pk)


@batch_advisor_required
@require_http_methods(["GET", "POST"])
def advisor_schedule(request):
    form = ScheduleForm(request.POST if request.method == "POST" else None, advisor=request.user)
    warnings, token = [], ""
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        warnings, token = _unacknowledged_overlap(request, data["starts_at"], data["duration"])
        if not warnings:
            try:
                meeting = services.schedule(request.user, data["student"], reason=data["reason"],
                                            starts_at=data["starts_at"], duration=data["duration"],
                                            location=data["location"])
            except ValidationError as error:
                _add_service_errors(form, error)
            else:
                messages.success(request, "Meeting scheduled. The student has been notified.")
                return redirect("advisor_meeting_detail", pk=meeting.pk)
    invalid = form.is_bound and bool(form.errors)
    return render(request, "meetings/schedule.html", {
        "form": form, "overlap_warnings": warnings, "overlap_token": token,
    }, status=400 if invalid else 200)


@batch_advisor_required
def advisor_month(request):
    return _render_month(request, "advisor_meetings", "advisor_meeting_detail")


@batch_advisor_required
def advisor_week(request):
    return _render_week(request, "advisor_meetings", "advisor_meeting_detail")


# --- Super Admin (read-only) -------------------------------------------------------------------

def _meeting_cohorts(visible):
    """(value, label) filter choices for the cohorts that have meetings, in academic order."""
    by_cohort = {cohort_value(m.batch_id, m.semester_id, m.section_id): m for m in visible.order_by()}
    ordered = merge_sort(
        list(by_cohort.items()),
        key=lambda pair: (pair[1].batch.name, pair[1].semester.number, pair[1].section.name),
    )
    return [(value, f"{m.batch} · {m.semester} · {m.section}") for value, m in ordered]


@super_admin_required
def super_admin_meetings(request):
    visible = visible_meetings(request.user)
    filters = FilterForm(request.GET, cohorts=_meeting_cohorts(visible))
    rows = visible.order_by()
    if filters.value("status"):
        rows = rows.filter(status=filters.value("status"))
    if filters.value("cohort"):  # validated against the offered choices
        batch_id, semester_id, section_id = (int(part) for part in filters.value("cohort").split("."))
        rows = rows.filter(batch_id=batch_id, semester_id=semester_id, section_id=section_id)
    page = Paginator(latest_first(list(rows)), ADMIN_PAGE_SIZE).get_page(request.GET.get("page"))
    decorate(page.object_list)
    state = urlencode([(key, filters.value(key)) for key in ("status", "cohort") if filters.value(key)])
    return render(request, "meetings/super_admin.html", {
        "filters": filters, "page": page, "page_state": state, "has_filters": bool(state),
        "stats": meeting_stats(visible.order_by()),
        "current": {name: filters.value(name) for name in ("status", "cohort")},
        "list_keys": ("status", "cohort", "page"),
        "view_urls": VIEW_URLS["super_admin_meetings"],
    })


@super_admin_required
def super_admin_month(request):
    return _render_month(request, "super_admin_meetings", "super_admin_meeting_detail")


@super_admin_required
def super_admin_week(request):
    return _render_week(request, "super_admin_meetings", "super_admin_meeting_detail")


@super_admin_required
def super_admin_meeting_detail(request, pk):
    """Read-only oversight (DEC-262): no forms and no POST route."""
    meeting = get_visible_meeting(request.user, pk)
    decorate([meeting])
    return render(request, "meetings/detail.html", {
        "meeting": meeting,
        "viewer_is_admin": True,
        "list_url_name": "super_admin_meetings",
        "student_post": current_post(meeting.student),
        "events": meeting.events.select_related("actor"),
    })
