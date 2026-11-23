"""
What the three home dashboards show. Views stay thin; every figure starts from the existing
visibility helpers (visible_complaints, visible_submissions, visible_meetings).

Super Admin privacy (DEC-315, DEC-318, DEC-319): nothing is calculated unless build_overview says
"ready". Cohort figures come only from its displayable cells, chart scales use visible values only,
and Recent activity covers visible cohorts in the term, without student names or links.
"""

from datetime import timedelta
from functools import reduce
from operator import or_

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from complaints.models import Complaint, ComplaintEvent
from complaints.permissions import visible_complaints
from complaints.presentation import status_journey, status_tone
from meetings.models import Meeting
from meetings.permissions import visible_meetings
from meetings.presentation import decorate, split_upcoming
from voice.models import Submission
from voice.permissions import visible_submissions

Status = Complaint.Status
Kind = ComplaintEvent.Kind
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)
ACTIVITY_LIMIT = 6
UPCOMING_LIMIT = 3
CHART_WEEKS = 12
SHADE_LEVELS = 4


# --- Chart geometry ------------------------------------------------------------------------------

def _nice_max(value):
    """A round axis maximum at or above `value`, always divisible by two."""
    value = max(value, 2)
    magnitude = 10 ** (len(str(value)) - 1)
    for step in (1, 2, 4, 6, 8, 10):
        candidate = magnitude * step
        if candidate >= value and candidate % 2 == 0:
            return candidate
    return magnitude * 10


def _number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def line_chart(labels, values):
    """Geometry for the line partial in a 100 x 100 box; None when there is nothing to plot."""
    if not any(values):
        return None
    top = _nice_max(max(values))
    count = len(values)
    points = []
    for index, (label, value) in enumerate(zip(labels, values)):
        x = 50.0 if count == 1 else index * 100 / (count - 1)
        y = 100 - value * 100 / top
        points.append({"x": _number(x), "y": _number(y), "label": label, "value": value})
    middle = labels[count // 2]
    return {
        "path": "M" + " L".join(f"{p['x']} {p['y']}" for p in points),
        "points": points,
        "y_ticks": [top, top // 2, 0],
        "x_labels": [labels[0], middle, labels[-1]] if count > 2 else list(labels),
        "desc": "; ".join(f"{label}: {value}" for label, value in zip(labels, values)),
    }


def bar_rows(rows):
    """Adds each row's width, scaled to the largest value shown."""
    top = max((row["value"] for row in rows), default=0)
    return [{**row, "width": _number(row["value"] * 100 / top) if top else "0"} for row in rows]


def stacked(segments):
    """Consecutive segments of one bar in a 100-wide box. A zero segment draws nothing."""
    total = sum(segment["value"] for segment in segments)
    if not total:
        return []
    start, drawn = 0.0, []
    for segment in segments:
        if segment["value"]:
            width = segment["value"] * 100 / total
            drawn.append({**segment, "x": _number(start), "width": _number(width)})
            start += width
    return drawn


def shade(count, top):
    """1 (light) to 4 (dark) Forest, relative to the largest visible cell; 0 for no complaints."""
    if not count or not top:
        return 0
    return min(SHADE_LEVELS, max(1, -(-count * SHADE_LEVELS // top)))


# --- Activity ------------------------------------------------------------------------------------

ACTIVITY_TEXT = {
    Kind.SUBMITTED: "submitted",
    Kind.RESPONSE: "responded on",
    Kind.FURTHER_INFORMATION: "added information to",
    Kind.STILL_NOT_RESOLVED: "reopened",
    Kind.CANCELLATION_REQUESTED: "asked to cancel",
    Kind.RESPONSIBLE_CHANGED: "changed the owner of",
}


def _activity_item(event, *, name_students, url_name):
    complaint = event.complaint
    by_student = event.actor_id == complaint.student_id
    who = (complaint.student.get_full_name() if name_students else "A student") if by_student else event.actor.get_full_name()
    if event.kind == Kind.STATUS_CHANGED:
        what = f"moved {complaint.reference} to {event.get_to_status_display()}"
    else:
        what = f"{ACTIVITY_TEXT.get(event.kind, 'updated')} {complaint.reference}"
    return {"who": who, "what": what, "when": event.created_at,
            "url": reverse(url_name, args=[complaint.reference]) if url_name else ""}


def _activity(complaints, *, exclude_kinds=(), name_students, url_name):
    events = (ComplaintEvent.objects.filter(complaint__in=complaints.order_by().values("pk"))
              .exclude(kind__in=exclude_kinds).select_related("actor", "complaint__student")
              .order_by("-created_at", "-id")[:ACTIVITY_LIMIT])
    return [_activity_item(event, name_students=name_students, url_name=url_name) for event in events]


# --- Super Admin ---------------------------------------------------------------------------------

def _weekly(in_window, term):
    start, end = term.window()
    first = timezone.localtime(start).date()
    last = min(timezone.localtime(end - timedelta(microseconds=1)).date(), timezone.localdate())
    if last < first:
        return None, ""
    monday = last - timedelta(days=last.weekday())
    weeks = []
    while monday + timedelta(days=6) >= first and len(weeks) < CHART_WEEKS:
        weeks.insert(0, monday)
        monday -= timedelta(days=7)
    counts = dict.fromkeys(weeks, 0)
    for created_at in in_window.order_by().values_list("created_at", flat=True):
        day = timezone.localtime(created_at).date()
        week = day - timedelta(days=day.weekday())
        if week in counts:
            counts[week] += 1
    labels = [f"{week.day} {week:%b}" for week in weeks]
    values = [counts[week] for week in weeks]
    chart = line_chart(labels, values)
    if chart is None:
        return None, ""
    peak = max(values)
    return chart, f"Busiest week began {labels[values.index(peak)]}: {peak} complaint{'' if peak == 1 else 's'}."


def super_admin_dashboard(user, overview):
    """Cards for a "ready" Overview. Any other state returns nothing, so nothing can be shown."""
    if overview.state != "ready":
        return {}
    received, review, rejected = overview.not_resolved_parts
    start, end = overview.term.window()
    in_window = visible_complaints(user).filter(created_at__gte=start, created_at__lt=end)

    cells = [cell for row in overview.rows for cell in row.cells if cell.state in ("count", "zero")]
    top = max((cell.count for cell in cells), default=0)
    rows = [{
        "semester": row.semester, "batch": row.batch,
        "cells": [{"cell": cell, "shade": shade(cell.count, top) if cell.state == "count" else 0} for cell in row.cells],
    } for row in overview.rows]

    activity = []
    if overview.visible_cohorts:
        visible_only = reduce(or_, (Q(batch_id=b, semester_id=s, section_id=c) for b, s, c in overview.visible_cohorts))
        activity = _activity(in_window.filter(visible_only), name_students=False, url_name=None)

    weekly, weekly_takeaway = _weekly(in_window, overview.term)
    return {
        "stats": [
            {"value": overview.total, "label": "Total this term", "icon": "file", "tone": "accent"},
            {"value": received.count + review.count, "label": "Open", "icon": "clock", "tone": "review"},
            {"value": overview.resolved.count, "label": "Resolved", "icon": "check", "tone": "resolved"},
            {"value": rejected.count, "label": "Rejected", "icon": "x", "tone": "rejected"},
        ],
        "weekly": weekly,
        "weekly_takeaway": weekly_takeaway,
        "category_bars": bar_rows([
            {"label": c.label, "value": c.count, "note": c.percent_label, "url": c.url, "inactive": c.inactive}
            for c in overview.categories
        ]),
        "section_bars": bar_rows([{"label": cell.label, "value": cell.count, "url": cell.url} for cell in cells]),
        "grid_rows": rows,
        "status_segments": stacked([
            {"key": "resolved", "label": "Resolved", "value": overview.resolved.count},
            {"key": "open", "label": "Open", "value": received.count + review.count},
            {"key": "rejected", "label": "Rejected", "value": rejected.count},
        ]),
        "open_count": received.count + review.count,
        "received": received, "review": review, "rejected": rejected,
        "activity": activity,
    }


# --- Batch Advisor -------------------------------------------------------------------------------

def _upcoming_meetings(visible, viewer):
    confirmed = list(visible.filter(status=Meeting.Status.CONFIRMED).order_by())
    upcoming, _closed = split_upcoming(confirmed)
    return decorate(upcoming[:UPCOMING_LIMIT], viewer)


def advisor_dashboard(user, assignments):
    complaints = visible_complaints(user)
    by_status = dict(complaints.order_by().values_list("status").annotate(n=Count("id")))
    received, review = by_status.get(Status.RECEIVED, 0), by_status.get(Status.UNDER_REVIEW, 0)
    resolved_recently = sum(a.counts["resolved_recently"] for a in assignments)
    waiting = visible_submissions(user).filter(status=Submission.Status.WAITING).count()
    return {
        "stats": [
            {"value": received + review, "label": "Open", "icon": "inbox", "tone": "accent"},
            {"value": received, "label": "Received", "icon": "file", "tone": "received"},
            {"value": review, "label": "Under review", "icon": "clock", "tone": "review"},
            {"value": resolved_recently, "label": "Resolved (7 days)", "icon": "check", "tone": "resolved"},
        ],
        "cohort_bars": bar_rows([
            {"label": f"{a.section.name} · S{a.semester.number}", "value": a.counts["open"], "url": a.complaints_url}
            for a in assignments
        ]),
        "has_open": bool(received + review),
        "meetings": _upcoming_meetings(visible_meetings(user), user),
        # The Batch Advisor history keeps owner changes hidden (Complaints Part 3).
        "activity": _activity(complaints, exclude_kinds=(Kind.RESPONSIBLE_CHANGED,), name_students=True,
                              url_name="advisor_complaint_detail"),
        "voice_waiting": waiting,
    }


# --- Student -------------------------------------------------------------------------------------

def student_dashboard(user):
    """The student's own numbers only."""
    complaints = visible_complaints(user)
    by_status = dict(complaints.order_by().values_list("status").annotate(n=Count("id")))
    open_count = sum(by_status.get(status, 0) for status in OPEN_STATUSES)
    answers = visible_submissions(user).exclude(answer="").count()
    all_upcoming, _closed = split_upcoming(list(visible_meetings(user).filter(status=Meeting.Status.CONFIRMED).order_by()))
    open_complaints = list(complaints.filter(status__in=OPEN_STATUSES).order_by("-created_at", "-pk")[:5])
    for complaint in open_complaints:
        complaint.tone = status_tone(complaint.status)
        complaint.journey = status_journey(complaint)
    return {
        "stats": [
            {"value": open_count, "label": "Open complaints", "icon": "file", "tone": "review", "url": reverse("student_complaints")},
            {"value": by_status.get(Status.RESOLVED, 0), "label": "Resolved complaints", "icon": "check", "tone": "resolved",
             "url": f"{reverse('student_complaints')}?status={Status.RESOLVED}"},
            {"value": answers, "label": "Student Voice answers", "icon": "voice", "tone": "accent", "url": reverse("student_voice")},
            {"value": len(all_upcoming), "label": "Upcoming meetings", "icon": "calendar", "tone": "received", "url": reverse("student_meetings")},
        ],
        "meetings": decorate(all_upcoming[:UPCOMING_LIMIT], user),
        "open_complaints": open_complaints,
    }
