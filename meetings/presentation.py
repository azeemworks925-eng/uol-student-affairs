"""How meetings appear: lists, the overlap warning, the Google Calendar link, the month view and
Student Home updates. All ordering uses dsa.sorting.merge_sort."""

import calendar
import re
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone
from django.utils.text import Truncator

from complaints.presentation import HOME_UPDATE_LIMIT, StudentUpdate
from dsa.intervals import overlaps_with
from dsa.sorting import merge_sort
from notifications.models import Notification
from voice.presentation import student_home_updates as complaint_and_voice_updates

from .models import Meeting, MeetingEvent

Status = Meeting.Status
Kind = MeetingEvent.Kind

# The existing status pill colours in static/css/app.css.
STATUS_TONES = {
    Status.REQUESTED: "received",
    Status.TIME_SUGGESTED: "review",
    Status.CONFIRMED: "resolved",
    Status.DECLINED: "rejected",
    Status.CANCELLED: "rejected",
}
GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/render"
MONTH_PATTERN = re.compile(r"(\d{4})-(\d{2})")
FIRST_YEAR, LAST_YEAR = 2000, 2100


def local_datetime(day, at):
    """A date and a time entered in the portal's time zone (Asia/Karachi), as an aware datetime."""
    return timezone.make_aware(datetime.combine(day, at), timezone.get_default_timezone())


def _day_start(day):
    return local_datetime(day, time.min)


# --- Lists -----------------------------------------------------------------------------------

def google_calendar_url(meeting, viewer):
    """A prefilled "new event" link. The private reason is left out because the link goes to Google."""
    other = meeting.advisor if viewer.pk == meeting.student_id else meeting.student
    start = meeting.starts_at.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end = meeting.ends_at.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{GOOGLE_CALENDAR_URL}?" + urlencode({
        "action": "TEMPLATE",
        "text": f"Meeting with {other.get_full_name()}",
        "dates": f"{start}/{end}",
        "details": "UOL Student Affairs meeting. The portal has the latest status.",
        "location": meeting.location,
    })


def decorate(meetings, viewer=None, now=None):
    """Add what the templates need. `viewer` is left out for read-only oversight."""
    now = now or timezone.now()
    for meeting in meetings:
        meeting.tone = STATUS_TONES[meeting.status]
        meeting.has_started = meeting.starts_at is not None and meeting.starts_at <= now
        meeting.calendar_url = (
            google_calendar_url(meeting, viewer) if viewer is not None and meeting.is_confirmed else ""
        )
    return meetings


def by_start(meetings):
    return merge_sort(meetings, key=lambda m: (m.when, m.pk))


def latest_first(meetings):
    return merge_sort(meetings, key=lambda m: (m.when, m.pk), reverse=True)


def is_upcoming(meeting, now):
    """Open requests and suggestions, and confirmed meetings that have not ended."""
    if meeting.is_requested or meeting.is_time_suggested:
        return True
    return meeting.is_confirmed and meeting.ends_at > now


def split_upcoming(meetings, now=None):
    now = now or timezone.now()
    upcoming = [m for m in meetings if is_upcoming(m, now)]
    closed = [m for m in meetings if not is_upcoming(m, now)]
    return by_start(upcoming), latest_first(closed)


def day_label(day, today):
    if day < today:
        return "Earlier"
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%A} {day.day} {day:%B}"


def group_by_day(ordered, today=None):
    """Consecutive meetings of a start-sorted list, grouped under Today, Tomorrow or their date."""
    today = today or timezone.localdate()
    groups = []
    for meeting in ordered:
        label = day_label(timezone.localtime(meeting.when).date(), today)
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "meetings": []})
        groups[-1]["meetings"].append(meeting)
    return groups


# --- Overlap warning -------------------------------------------------------------------------

def overlap_warnings(advisor, starts_at, duration, exclude_pk=None):
    """One sentence for each of the advisor's Confirmed meetings that day overlapping this time."""
    day = timezone.localtime(starts_at).date()
    same_day = Meeting.objects.select_related("student").filter(
        advisor=advisor, status=Status.CONFIRMED,
        starts_at__gte=_day_start(day), starts_at__lt=_day_start(day + timedelta(days=1)),
    ).exclude(pk=exclude_pk).order_by()
    others = [(m.starts_at, m.ends_at, m) for m in same_day]
    target = (starts_at, starts_at + timedelta(minutes=duration), None)
    warnings = []
    for start, end, meeting in overlaps_with(target, others):
        warnings.append(
            f"You already have a meeting from {timezone.localtime(start):%H:%M} to "
            f"{timezone.localtime(end):%H:%M} with {meeting.student.get_full_name()}."
        )
    return warnings


def overlap_token(starts_at, duration):
    """Identifies the exact time the advisor was warned about, so changing it warns again."""
    return f"{starts_at:%Y%m%d%H%M}-{duration}"


# --- Month view ------------------------------------------------------------------------------

def parse_month(value, today):
    """(year, month) from "YYYY-MM". Anything invalid means the current month."""
    match = MONTH_PATTERN.fullmatch(value or "")
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if FIRST_YEAR <= year <= LAST_YEAR and 1 <= month <= 12:
            return year, month
    return today.year, today.month


def _shift(year, month, step):
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1


def _selected_day(value, year, month, today):
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        day = today
    if (day.year, day.month) != (year, month):
        return today if (today.year, today.month) == (year, month) else None
    return day


def build_month(visible, month_value, day_value, viewer=None):
    """The month grid: Confirmed meetings only, one row per week, Monday first."""
    today = timezone.localdate()
    year, month = parse_month(month_value, today)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    first, last = weeks[0][0], weeks[-1][-1]
    rows = list(visible.filter(
        status=Status.CONFIRMED, starts_at__gte=_day_start(first), starts_at__lt=_day_start(last + timedelta(days=1)),
    ).order_by())
    by_day = {}
    for meeting in by_start(rows):
        by_day.setdefault(timezone.localtime(meeting.starts_at).date(), []).append(meeting)

    current = f"{year:04d}-{month:02d}"
    selected = _selected_day(day_value, year, month, today)
    grid = []
    for week in weeks:
        cells = []
        for day in week:
            count = len(by_day.get(day, ()))
            cells.append({
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "is_selected": day == selected,
                "count": count,
                "query": urlencode({"month": current, "day": day.isoformat()}),
            })
        grid.append(cells)
    day_meetings = by_day.get(selected, []) if selected else []
    decorate(day_meetings, viewer)
    previous_year, previous_month = _shift(year, month, -1)
    next_year, next_month = _shift(year, month, 1)
    return {
        "title": date(year, month, 1),
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "weeks": grid,
        "selected": selected,
        "day_meetings": day_meetings,
        "previous": f"{previous_year:04d}-{previous_month:02d}",
        "next": f"{next_year:04d}-{next_month:02d}",
    }


# --- Student Home ----------------------------------------------------------------------------

HOME_KINDS = (Kind.CONFIRMED, Kind.SCHEDULED, Kind.SUGGESTED, Kind.DECLINED, Kind.CANCELLED)
HOME_TEXT = {
    Kind.CONFIRMED: ("Meeting confirmed", "Your meeting is confirmed."),
    Kind.SCHEDULED: ("Meeting scheduled", "Your Batch Advisor scheduled a meeting."),
    Kind.SUGGESTED: ("New time suggested", "Your Batch Advisor suggested a meeting time."),
    Kind.DECLINED: ("Meeting declined", "Your meeting request was declined."),
    Kind.CANCELLED: ("Meeting cancelled", "Your meeting was cancelled."),
}


def meeting_updates(student, limit=HOME_UPDATE_LIMIT):
    """The student's latest advisor actions on their meetings, newest first."""
    events = list(
        MeetingEvent.objects.filter(meeting__student=student, kind__in=HOME_KINDS)
        .exclude(actor=student).select_related("meeting").order_by()
    )
    latest = merge_sort(events, key=lambda e: (e.created_at, e.pk), reverse=True)[:limit]
    unread = set(
        Notification.objects.filter(
            recipient=student, source_type=MeetingEvent._meta.label_lower,
            source_id__in=[e.pk for e in latest], read_at__isnull=True,
        ).values_list("source_id", flat=True)
    )
    updates = []
    for event in latest:
        meeting = event.meeting
        label, headline = HOME_TEXT[event.kind]
        updates.append(StudentUpdate(
            reference="Meeting", complaint_title=Truncator(meeting.reason).chars(60), headline=headline,
            label=label, status=meeting.status, status_label=meeting.get_status_display(),
            tone=STATUS_TONES[meeting.status], when=event.created_at,
            url=reverse("student_meeting_detail", args=[meeting.pk]), is_new=event.pk in unread,
        ))
    return updates


def student_home_updates(student, limit=HOME_UPDATE_LIMIT):
    """Complaint, Student Voice and meeting updates merged, newest first, at most `limit`."""
    combined = [*complaint_and_voice_updates(student, limit), *meeting_updates(student, limit)]
    return merge_sort(combined, key=lambda update: update.when, reverse=True)[:limit]
