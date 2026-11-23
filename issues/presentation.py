"""How section issues appear on pages. All ordering uses dsa.sorting.merge_sort."""

from dsa.sorting import merge_sort

from .models import CollectiveIssue

Status = CollectiveIssue.Status

STATUS_TONES = {Status.RECEIVED: "received", Status.UNDER_REVIEW: "review", Status.RESOLVED: "resolved"}
JOURNEY = (Status.RECEIVED, Status.UNDER_REVIEW, Status.RESOLVED)


def newest_first(issues):
    return merge_sort(list(issues), key=lambda issue: (issue.created_at, issue.pk), reverse=True)


def add_display(issues):
    for issue in issues:
        issue.tone = STATUS_TONES[issue.status]
        issue.support_label = "Open for support" if issue.support_is_open else "Support closed"
    return issues


def status_journey(issue):
    """Received → Under Review → Resolved, marking where the issue is now."""
    current = JOURNEY.index(issue.status)
    return [{"label": step.label, "state": "done" if index < current else "current" if index == current else "upcoming"}
            for index, step in enumerate(JOURNEY)]


def private_responses(issue):
    """Official responses and the resolution note, newest first. Never for non-representatives."""
    events = issue.events.exclude(message="").select_related("actor")
    return merge_sort(list(events), key=lambda event: (event.created_at, event.pk), reverse=True)


def supported_ids(user, issues):
    """Which of these issues this user has supported. Only ever about the user themselves."""
    return set(user.issue_supports.filter(issue__in=[issue.pk for issue in issues]).values_list("issue_id", flat=True))
