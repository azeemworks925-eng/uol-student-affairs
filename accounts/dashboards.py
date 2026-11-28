"""
What the three home dashboards show. Views stay thin; every figure starts from the existing
visibility helpers (visible_complaints, visible_issues, visible_submissions, visible_meetings), so
a home never counts anything its user cannot open.

Same stat, same definition (Polish v2): each stat a home shows is computed by one function in the
"Shared stats" section below, whichever home shows it.
"""

from datetime import time, timedelta
from math import cos, pi, sin

from django.urls import reverse
from django.utils import timezone

from academics import services as term_services
from complaints.models import Complaint, ComplaintEvent
from complaints.ordering import next_waiting
from complaints.permissions import visible_complaints
from complaints.presentation import status_journey, status_tone
from issues.models import CollectiveIssue
from issues.permissions import visible_issues
from meetings.models import Meeting
from meetings.permissions import visible_meetings
from meetings.presentation import decorate, local_datetime, split_upcoming
from voice.models import Submission
from voice.permissions import visible_submissions
from voice.presentation import add_tones

Status = Complaint.Status
Kind = ComplaintEvent.Kind
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)
ACTIVITY_LIMIT = 6
CARD_LIMIT = 3
CHART_WEEKS = 12


# --- Shared stats: one definition each -------------------------------------------------------------

def open_complaints(complaints):
    """Open complaints: Received or Under review."""
    return complaints.filter(status__in=OPEN_STATUSES).count()


def issues_waiting(issues):
    """Section issues no Batch Advisor has acted on yet: still Received."""
    return issues.filter(status=CollectiveIssue.Status.RECEIVED)


def voice_waiting(submissions):
    """Student Voice submissions no Batch Advisor has answered or reviewed yet."""
    return submissions.filter(status=Submission.Status.WAITING)


def voice_answers(submissions):
    """Student Voice submissions with an answer or a reply."""
    return submissions.exclude(answer="")


def upcoming_meetings(meetings):
    """Confirmed meetings that have not ended, soonest first."""
    upcoming, _closed = split_upcoming(list(meetings.filter(status=Meeting.Status.CONFIRMED).order_by()))
    return upcoming


def meetings_this_week(meetings, today=None):
    """Confirmed meetings starting this week (Monday to Sunday, Pakistan time)."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    start, end = local_datetime(monday, time.min), local_datetime(monday + timedelta(days=7), time.min)
    return meetings.filter(status=Meeting.Status.CONFIRMED, starts_at__gte=start, starts_at__lt=end)


def stat(value, label, icon, tone, url=""):
    return {"value": value, "label": label, "icon": icon, "tone": tone, "url": url}


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


def _smooth(points):
    """A smooth curve through the points (Catmull-Rom as cubic Béziers), kept inside the box."""
    xy = [(float(p["x"]), float(p["y"])) for p in points]
    if len(xy) < 3:
        return "M" + " L".join(f"{_number(x)} {_number(y)}" for x, y in xy)
    path = [f"M{_number(xy[0][0])} {_number(xy[0][1])}"]
    for i in range(len(xy) - 1):
        p0, p1, p2 = xy[max(i - 1, 0)], xy[i], xy[i + 1]
        p3 = xy[min(i + 2, len(xy) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(max(p1[1] + (p2[1] - p0[1]) / 6, 0), 100))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(max(p2[1] - (p3[1] - p1[1]) / 6, 0), 100))
        path.append(f"C{_number(c1[0])} {_number(c1[1])} {_number(c2[0])} {_number(c2[1])} {_number(p2[0])} {_number(p2[1])}")
    return " ".join(path)


def line_chart(labels, values):
    """Geometry for the area chart partial in a 100 x 100 box; None when there is nothing to plot."""
    if not any(values):
        return None
    top = _nice_max(max(values))
    count = len(values)
    points = []
    for index, (label, value) in enumerate(zip(labels, values)):
        x = 50.0 if count == 1 else index * 100 / (count - 1)
        y = 100 - value * 100 / top
        points.append({"x": _number(x), "y": _number(y), "label": label, "value": value,
                       "edge": "is-flip" if x > 66 else ("is-start" if x < 34 else "")})
    middle = labels[count // 2]
    smooth = _smooth(points)
    return {
        "path": "M" + " L".join(f"{p['x']} {p['y']}" for p in points),
        "smooth": smooth,
        "area": f"{smooth} L{points[-1]['x']} 100 L{points[0]['x']} 100 Z",
        "points": points,
        "y_ticks": [top, top // 2, 0],
        "x_labels": [labels[0], middle, labels[-1]] if count > 2 else list(labels),
        "desc": "; ".join(f"{label}: {value}" for label, value in zip(labels, values)),
    }


def bar_rows(rows):
    """Adds each row's width, scaled to the largest value shown."""
    top = max((row["value"] for row in rows), default=0)
    return [{**row, "width": _number(row["value"] * 100 / top) if top else "0"} for row in rows]


def donut(segments):
    """Arcs of a ring with circumference 100 (r = 15.915), drawn from 12 o'clock. A zero segment
    draws nothing. Each arc gets its dash length and offset, and its label position for a tooltip."""
    total = sum(segment["value"] for segment in segments)
    if not total:
        return []
    start, drawn = 0.0, []
    for segment in segments:
        if segment["value"]:
            length = segment["value"] * 100 / total
            middle = (start + length / 2) / 100 * 2 * pi - pi / 2
            drawn.append({**segment, "length": _number(length), "gap": _number(100 - length),
                          "offset": _number(25 - start),
                          "tip_x": _number(50 + 50 * cos(middle)), "tip_y": _number(50 + 50 * sin(middle))})
            start += length
    return drawn


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
    anonymous = by_student and not name_students
    who = ("A student" if anonymous else complaint.student.get_full_name()) if by_student else event.actor.get_full_name()
    if event.kind == Kind.STATUS_CHANGED:
        what = f"moved {complaint.reference} to {event.get_to_status_display()}"
    else:
        what = f"{ACTIVITY_TEXT.get(event.kind, 'updated')} {complaint.reference}"
    return {"who": who, "what": what, "when": event.created_at, "anonymous": anonymous,
            "tone": status_tone(complaint.status),
            "url": reverse(url_name, args=[complaint.reference])}


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
    return chart, f"Busiest week: {labels[values.index(peak)]}, {peak} complaint{'' if peak == 1 else 's'}."


def super_admin_dashboard(user, overview):
    """The Overview's cards for the current term. Nothing without a current term."""
    if overview.state != "ready":
        return {}
    received, review, rejected = overview.not_resolved_parts
    start, end = overview.term.window()
    in_window = visible_complaints(user).filter(created_at__gte=start, created_at__lt=end)
    list_url = reverse("super_admin_complaints")
    term_query = f"?term={overview.term.pk}"
    open_count = open_complaints(in_window)
    total = overview.total
    resolved_percent = overview.resolved.percent_label if total else ""

    weekly, weekly_takeaway = _weekly(in_window, overview.term)
    return {
        "stats": [
            stat(total, "Complaints", "file", "accent", list_url + term_query),
            stat(open_count, "Open complaints", "clock", "review", f"{list_url}{term_query}&status=open"),
            stat(overview.resolved.count, "Resolved", "check", "resolved", overview.resolved.url),
            stat(rejected.count, "Rejected", "x", "rejected", rejected.url),
        ],
        "weekly": weekly,
        "weekly_takeaway": weekly_takeaway,
        "category_bars": bar_rows([
            {"label": c.label, "value": c.count, "note": c.percent_label, "url": c.url, "inactive": c.inactive}
            for c in overview.categories
        ]),
        "section_bars": bar_rows([
            {"label": c.short_label, "title": c.label, "value": c.count, "url": c.url} for c in overview.cohorts
        ]),
        "donut": donut([
            {"key": "resolved", "label": "Resolved", "value": overview.resolved.count, "url": overview.resolved.url},
            {"key": "open", "label": "Open", "value": open_count, "url": f"{list_url}{term_query}&status=open"},
            {"key": "rejected", "label": "Rejected", "value": rejected.count, "url": rejected.url},
        ]),
        "donut_centre": resolved_percent,
        "open_count": open_count,
        "received": received, "review": review, "rejected": rejected,
        # Every cohort; students stay anonymous on the Overview.
        "activity": _activity(in_window, name_students=False, url_name="super_admin_complaint_detail"),
        "activity_url": list_url,
    }


# --- Batch Advisor -------------------------------------------------------------------------------

def next_complaint(complaints, today=None):
    """The hero's "Next complaint": the oldest complaint still waiting (a min-heap, dsa/heap.py),
    and how many days it has waited. None when nothing waits (All caught up)."""
    oldest = next_waiting(complaints)
    if oldest is None:
        return None
    days = ((today or timezone.localdate()) - timezone.localtime(oldest.created_at).date()).days
    return {"reference": oldest.reference, "days": days,
            "since": timezone.localtime(oldest.created_at)}


def advisor_dashboard(user, assignments):
    complaints = visible_complaints(user)
    issues = visible_issues(user)
    submissions = visible_submissions(user)
    meetings = visible_meetings(user)
    waiting_voice = voice_waiting(submissions)
    waiting_issues = issues_waiting(issues)
    voice_items = add_tones(list(waiting_voice.select_related("student").order_by("-created_at", "-pk")[:CARD_LIMIT]))
    issue_items = list(waiting_issues.select_related("raised_by").order_by("-created_at", "-pk")[:CARD_LIMIT])
    upcoming = upcoming_meetings(meetings)
    return {
        "stats": [
            stat(open_complaints(complaints), "Open complaints", "file", "review", reverse("advisor_complaints") + "?status=open"),
            stat(waiting_issues.count(), "Issues waiting", "hand", "received", reverse("advisor_issues") + "?status=received"),
            stat(waiting_voice.count(), "Voice waiting", "voice", "lavender", reverse("advisor_voice") + "?status=waiting"),
            stat(meetings_this_week(meetings).count(), "Meetings this week", "calendar", "resolved", reverse("advisor_meetings")),
        ],
        "next": next_complaint(complaints),
        "term": term_services.current_term(),
        "cohort_bars": bar_rows([
            {"label": f"{a.section.name} · S{a.semester.number}", "title": f"{a.batch} · {a.semester} · {a.section}",
             "value": a.counts["open"], "url": a.complaints_url}
            for a in assignments
        ]),
        "has_open": any(a.counts["open"] for a in assignments),
        "meetings": decorate(upcoming[:CARD_LIMIT], user),
        # The Batch Advisor history keeps owner changes hidden (Complaints Part 3).
        "activity": _activity(complaints, exclude_kinds=(Kind.RESPONSIBLE_CHANGED,), name_students=True,
                              url_name="advisor_complaint_detail"),
        "voice_items": voice_items,
        "issue_items": issue_items,
    }


# --- Student -------------------------------------------------------------------------------------

def student_dashboard(user):
    """The student's own numbers only."""
    complaints = visible_complaints(user)
    submissions = visible_submissions(user)
    upcoming = upcoming_meetings(visible_meetings(user))
    resolved = complaints.filter(status=Status.RESOLVED).count()
    open_list = list(complaints.filter(status__in=OPEN_STATUSES).order_by("-created_at", "-pk")[:4])
    for complaint in open_list:
        complaint.tone = status_tone(complaint.status)
        complaint.journey = status_journey(complaint)
    answers = list(voice_answers(submissions).order_by("-answered_at", "-pk")[:CARD_LIMIT])
    complaints_url = reverse("student_complaints")
    return {
        "stats": [
            stat(open_complaints(complaints), "Open complaints", "file", "review", complaints_url + "?status=open"),
            stat(resolved, "Resolved", "check", "resolved", f"{complaints_url}?status={Status.RESOLVED}"),
            stat(voice_answers(submissions).count(), "Voice answers", "voice", "lavender",
                 reverse("student_voice") + "?status=answered"),
            stat(len(upcoming), "Upcoming meetings", "calendar", "received", reverse("student_meetings")),
        ],
        "meetings": decorate(upcoming[:CARD_LIMIT], user),
        "open_complaints": open_list,
        "answers": add_tones(answers),
    }
