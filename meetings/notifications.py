"""
Meeting notifications (DEC-270, DEC-328). Only the student is notified, and only when an advisor
confirms or schedules a meeting, suggests a time, declines, or cancels.

Called inside the service's transaction, so a rolled-back change leaves no notification.
"""

from django.utils import timezone
from django.utils.text import Truncator

from notifications.services import notify

from .models import MeetingEvent

Kind = MeetingEvent.Kind
PREVIEW_LIMIT = 140

# Event kind -> (notification type, title).
NOTICES = {
    Kind.CONFIRMED: ("meeting.confirmed", "Your meeting is confirmed"),
    Kind.SCHEDULED: ("meeting.confirmed", "Your Batch Advisor scheduled a meeting"),
    Kind.SUGGESTED: ("meeting.time_suggested", "Your Batch Advisor suggested a time"),
    Kind.DECLINED: ("meeting.declined", "Your meeting request was declined"),
    Kind.CANCELLED: ("meeting.cancelled", "Your meeting was cancelled"),
}


def _body(event):
    meeting = event.meeting
    if event.kind in (Kind.DECLINED, Kind.CANCELLED):
        return f"Reason: {Truncator(event.note).chars(PREVIEW_LIMIT)}"
    start = timezone.localtime(meeting.starts_at)
    return f"{start:%a %d %b %Y, %H:%M} · {meeting.duration_minutes} min · {meeting.location}"


def notify_student(event):
    """Send the notification for an advisor's action. A student's own action sends nothing."""
    if event.actor_id == event.meeting.student_id or event.kind not in NOTICES:
        return None
    event_type, title = NOTICES[event.kind]
    notification, _ = notify(
        event.meeting.student,
        event_type=event_type,
        source=event,
        title=title,
        body=_body(event),
        target_url_name="student_meeting_detail",
        target_arg=str(event.meeting_id),
    )
    return notification
