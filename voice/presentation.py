"""How Student Voice appears in lists and on Student Home. All ordering uses dsa.sorting.merge_sort."""

from django.urls import reverse
from django.utils.text import Truncator

from complaints.presentation import HOME_UPDATE_LIMIT, StudentUpdate, student_updates
from dsa.sorting import merge_sort
from notifications.models import Notification

from .models import Submission

Status = Submission.Status

# The existing status pill colours in static/css/app.css.
STATUS_TONES = {Status.WAITING: "received", Status.REVIEWED: "review", Status.ANSWERED: "resolved"}


def add_tones(submissions):
    for submission in submissions:
        submission.tone = STATUS_TONES[submission.status]
    return submissions


def sort_submissions(submissions, sort="newest"):
    """Merge sort by submission time: newest first unless "oldest" is chosen."""
    return merge_sort(submissions, key=lambda s: (s.created_at, s.pk), reverse=sort != "oldest")


def voice_updates(student, limit=HOME_UPDATE_LIMIT):
    """The student's latest answers and replies, newest first, in the Student Home row format."""
    answered = list(Submission.objects.filter(student=student).exclude(answer="").order_by())
    latest = merge_sort(answered, key=lambda s: (s.answered_at, s.pk), reverse=True)[:limit]
    unread = set(
        Notification.objects.filter(
            recipient=student, source_type=Submission._meta.label_lower,
            source_id__in=[s.pk for s in latest], read_at__isnull=True,
        ).values_list("source_id", flat=True)
    )
    updates = []
    for submission in latest:
        kind = submission.get_type_display().lower()
        label = "Your question was answered" if submission.is_question else f"Reply to your {kind}"
        headline = "Your question has an answer." if submission.is_question else f"Your {kind} has a reply."
        updates.append(StudentUpdate(
            reference="Student Voice", complaint_title=Truncator(submission.text).chars(60), headline=headline,
            label=label, status=submission.status, status_label=submission.get_status_display(),
            tone=STATUS_TONES[submission.status], when=submission.answered_at,
            url=reverse("student_voice_detail", args=[submission.pk]), is_new=submission.pk in unread,
        ))
    return updates


def student_home_updates(student, limit=HOME_UPDATE_LIMIT):
    """Complaint updates and Student Voice answers merged, newest first, at most `limit`."""
    combined = [*student_updates(student, limit), *voice_updates(student, limit)]
    return merge_sort(combined, key=lambda update: update.when, reverse=True)[:limit]
