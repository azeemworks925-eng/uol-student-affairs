"""
Complaint notification producers (COMPLAINTS_PART4_SPEC.md section 5.2; DEC-270).

Only two events notify, and only the student who submitted the complaint:
- a Batch Advisor or Super Admin changes the status (STATUS_CHANGED);
- a Batch Advisor or Super Admin responds (RESPONSE).

Called by complaints.services inside the same atomic transaction as the event, so a rolled-back
action leaves no notification. No other complaint event notifies anyone: not submission, further
information, "Still not resolved", cancellation requests or owner changes; and no Batch Advisor,
Super Admin or other student is ever a recipient.

Privacy: a status notification states the new status and the complaint's own title, never the
resolution note or rejection reason. A response notification previews the staff-authored text,
truncated, and attributes it by role only (as the student's history does), never by account name
or email. Text inside the response itself is left as written.
"""

from django.utils.text import Truncator

from notifications.services import notify

from .models import ComplaintEvent

Kind = ComplaintEvent.Kind
DESTINATION = "student_complaint_detail"
RESPONSE_PREVIEW_LIMIT = 140


def notify_student(event):
    """Create the notification for this immutable event, if it is one that notifies."""
    if event.kind not in (Kind.STATUS_CHANGED, Kind.RESPONSE):
        return None
    complaint = event.complaint
    recipient = complaint.student
    if event.actor_id == recipient.pk:
        return None  # never notify someone about their own action
    if event.kind == Kind.STATUS_CHANGED:
        title = f"{complaint.reference} is now {event.get_to_status_display()}"
        body = complaint.title
        event_type = "complaint.status_changed"
    else:
        title = f"New response on {complaint.reference}"
        body = f"{event.actor.get_role_display()}: {Truncator(event.message).chars(RESPONSE_PREVIEW_LIMIT)}"
        event_type = "complaint.response"
    notification, _ = notify(
        recipient,
        event_type=event_type,
        source=event,
        title=title,
        body=body,
        target_url_name=DESTINATION,
        target_arg=complaint.reference,
    )
    return notification
