"""How Student Voice appears in lists and on Student Home. All ordering uses dsa.sorting.merge_sort."""

from django.db.models import Count
from django.urls import reverse
from django.utils.text import Truncator

from accounts import tones

from complaints.presentation import HOME_UPDATE_LIMIT, StudentUpdate, student_updates
from dsa.sorting import merge_sort
from notifications.models import Notification

from .models import Submission

Status = Submission.Status

# The one status colour map (accounts.tones; docs/POLISH_V2.md).
STATUS_TONES = tones.VOICE


def add_tones(submissions):
    for submission in submissions:
        submission.tone = STATUS_TONES[submission.status]
    return submissions


def voice_stats(visible):
    """The stat cards of a Student Voice list, from what this user can see within the page's other
    filters. The three statuses are filter tabs; the total is not."""
    counts = dict(visible.order_by().values_list("status").annotate(n=Count("id")))
    return [
        {"value": sum(counts.values()), "label": "Total", "icon": "voice", "tone": "accent"},
        *({"value": counts.get(status, 0), "label": label, "icon": icon, "tone": STATUS_TONES[status],
           "param": "status", "filter": status}
          for status, label, icon in ((Status.WAITING, "Waiting", "clock"), (Status.REVIEWED, "Reviewed", "inbox"),
                                      (Status.ANSWERED, "Answered", "check"))),
    ]


PROGRESS = {Status.WAITING: "0.2", Status.REVIEWED: "0.6", Status.ANSWERED: "1"}


def list_display(submissions, *, show_cohort=False):
    """Tone, type pastel, progress, the second line and the type pill of each row or card."""
    for submission in add_tones(submissions):
        submission.pastel = tones.voice_type_pastel(submission.type)
        submission.progress = PROGRESS[submission.status]
        parts = [submission.get_type_display()]
        if show_cohort:
            parts.append(f"{submission.section.name} · S{submission.semester.number}")
        submission.preview = f"{submission.answer_label}: {Truncator(submission.answer).chars(80)}" if submission.answer else ""
        if submission.preview:
            parts.append(submission.preview)
        submission.secondary = " · ".join(parts)
        submission.chips = [{"label": submission.get_type_display(), "tone": submission.pastel}]
    return submissions


def status_journey(submission):
    """Waiting → (Reviewed, for ideas and feedback) → Answered, marking where it is now."""
    steps = [Status.WAITING] + ([] if submission.is_question else [Status.REVIEWED]) + [Status.ANSWERED]
    current = steps.index(submission.status) if submission.status in steps else len(steps) - 1
    return [{"label": Status(step).label, "state": "done" if i < current else "current" if i == current else "upcoming",
             "tone": STATUS_TONES[step]} for i, step in enumerate(steps)]


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


def timeline(submission, *, staff):
    """The submission's history for the timeline: sent, reviewed and the answer or reply. Students
    see staff by role only; staff see names with a role pill."""
    def who(user):
        return user.get_full_name() if staff else user.get_role_display()

    entries = [{"kind": "status", "title": "Sent" if staff else "You sent this", "when": submission.created_at,
                "tone": STATUS_TONES[Status.WAITING], "by": submission.student.get_full_name() if staff else ""}]
    if submission.reviewed_at:
        entries.append({"kind": "status", "title": "Reviewed", "when": submission.reviewed_at,
                        "tone": STATUS_TONES[Status.REVIEWED], "status_label": Status.REVIEWED.label,
                        "by": who(submission.reviewed_by)})
    if submission.answer:
        entries.append({"kind": "response", "title": submission.answer_label, "when": submission.answered_at,
                        "tone": STATUS_TONES[Status.ANSWERED], "by": who(submission.answered_by),
                        "by_role": submission.answered_by.get_role_display() if staff else "",
                        "message": submission.answer})
    return entries
