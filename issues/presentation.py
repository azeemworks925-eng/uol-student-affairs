"""How section issues appear on pages. All ordering uses dsa.sorting.merge_sort."""

from django.db.models import Q

from accounts import tones

from accounts.representation import current_period, current_representative
from dsa.sorting import merge_sort

from .models import CollectiveIssue
from .permissions import student_cohort, visible_issues

Status = CollectiveIssue.Status

STATUS_TONES = tones.ISSUE  # the one status colour map (accounts.tones)
JOURNEY = (Status.RECEIVED, Status.UNDER_REVIEW, Status.RESOLVED)
# The database form of CollectiveIssue.support_is_open, for the support filter.
SUPPORT_OPEN = Q(first_response_at__isnull=True, batch__is_active=True, semester__is_active=True,
                 section__is_active=True)


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


def issue_stats(issues):
    """The stat strip, from rows the user can already see."""
    rows = list(issues)
    return [
        {"value": sum(1 for i in rows if i.support_is_open), "label": "Open for support", "icon": "hand", "tone": "accent"},
        {"value": sum(1 for i in rows if i.status == Status.UNDER_REVIEW), "label": "Under review", "icon": "clock", "tone": "review"},
        {"value": sum(1 for i in rows if i.status == Status.RESOLVED), "label": "Resolved", "icon": "check", "tone": "resolved"},
        {"value": sum(i.support_total for i in rows), "label": "Total supports", "icon": "users", "tone": "received"},
    ]


def section_board(user):
    """The Student Home noticeboard: issues open for support in the student's cohort, newest first."""
    cohort = student_cohort(user)
    period = current_representative(user)
    can_raise = period is not None and all(
        entry.is_active for entry in (period.batch, period.semester, period.section)
    )
    open_issues = [i for i in visible_issues(user).filter(first_response_at__isnull=True).order_by() if i.support_is_open]
    issues = add_display(newest_first(open_issues))
    mine = supported_ids(user, issues)
    for issue in issues:
        issue.has_supported = issue.pk in mine
    return {
        "issues": issues,
        "is_rep": period is not None,
        "can_raise": can_raise,
        "awaiting": cohort is not None and current_period(cohort) is None,
    }
