"""
Section issue notifications (DEC-270, DEC-325). Called inside the service's transaction, so a
rolled-back action leaves no notification. The source is the IssueEvent, so each action creates
at most one notification per person. Advisor text is never copied into a notification.
"""

from accounts.representation import Cohort, active_members, current_period
from notifications.services import notify

DESTINATION = "student_issue_detail"


def notify_published(issue, event):
    """Every active student of the cohort except the author."""
    for student in active_members(Cohort.of(issue)).exclude(pk=issue.raised_by_id):
        notify(student, event_type="issue.published", source=event, title=f"New section issue: {issue.title}",
               body=issue.reference, target_url_name=DESTINATION, target_arg=issue.reference)


def notify_representatives(issue, event):
    """The cohort's CR and GR at the moment of the advisor's action, once per action."""
    cohort = Cohort.of(issue)
    period = current_period(cohort)
    if period is None:
        return
    resolved = event.is_resolution
    event_type = "issue.resolved" if resolved else "issue.response"
    title = "Your section's issue was resolved" if resolved else "Response to your section's issue"
    for representative in active_members(cohort).filter(pk__in=[period.cr_id, period.gr_id]):
        notify(representative, event_type=event_type, source=event, title=title,
               body=f"{issue.reference}: {issue.title}", target_url_name=DESTINATION, target_arg=issue.reference)
