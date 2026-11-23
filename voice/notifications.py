"""
Student Voice notifications (DEC-270). Only an answer or a reply notifies, and only the student
who submitted. Marking something reviewed does not notify. Staff are named by role only.

Called inside the service's transaction, so a rolled-back answer leaves no notification.
"""

from django.utils.text import Truncator

from notifications.services import notify

PREVIEW_LIMIT = 140


def notify_student(submission):
    if submission.is_question:
        event_type, title = "voice.answered", "Your question has an answer"
    else:
        event_type, title = "voice.replied", f"Your {submission.get_type_display().lower()} has a reply"
    notification, _ = notify(
        submission.student,
        event_type=event_type,
        source=submission,
        title=title,
        body=f"{submission.answered_by.get_role_display()}: {Truncator(submission.answer).chars(PREVIEW_LIMIT)}",
        target_url_name="student_voice_detail",
        target_arg=str(submission.pk),
    )
    return notification
