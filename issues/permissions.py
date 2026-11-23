"""
Who may see and act on section issues (DEC-243, DEC-246, DEC-247, DEC-324).

- Student: issues of their current exact cohort. Only the current CR and GR also see the full
  status and the private advisor responses.
- Batch Advisor: issues of their exactly assigned cohorts.
- Super Admin: every issue, read-only.

Views load records through `get_visible_issue`, so anything out of scope is a 404.
"""

from django.db.models import Count
from django.http import Http404

from accounts.models import AdvisorAssignment, StudentProfile
from accounts.permissions import assigned_cohort_filter
from accounts.representation import Cohort, current_representative

from .models import CollectiveIssue


def _active(user):
    return bool(user and user.is_authenticated and user.is_active)


def student_cohort(user):
    """The student's current exact cohort, or None."""
    row = StudentProfile.objects.filter(user_id=user.pk).values_list("batch_id", "semester_id", "section_id").first()
    return Cohort(*row) if row else None


def visible_issues(user):
    """The only starting point for reading issues. Each row carries `support_total`."""
    issues = (CollectiveIssue.objects.select_related("batch", "semester", "section", "raised_by")
              .annotate(support_total=Count("supports")))
    if not _active(user):
        return issues.none()
    if user.is_super_admin:
        return issues
    if user.is_batch_advisor:
        return issues.filter(assigned_cohort_filter(user))
    if user.is_student:
        cohort = student_cohort(user)
        return issues.filter(**cohort.filter()) if cohort else issues.none()
    return issues.none()


def get_visible_issue(user, reference):
    """The issue if the user may see it; otherwise 404, so its existence is not revealed."""
    try:
        return visible_issues(user).get(reference=reference)
    except CollectiveIssue.DoesNotExist:
        raise Http404("No issue found.") from None


def is_current_representative_of(user, issue):
    """Whether the user is the CR or GR of this issue's cohort right now (never a former one)."""
    period = current_representative(user)
    return period is not None and Cohort.of(period) == Cohort.of(issue)


def is_cohort_student(user, issue):
    return _active(user) and user.is_student and student_cohort(user) == Cohort.of(issue)


def can_act(user, issue):
    """Mark Under Review, respond, resolve: every advisor of the exact cohort (DEC-324)."""
    return _active(user) and user.is_batch_advisor and AdvisorAssignment.objects.filter(
        advisor=user, **Cohort.of(issue).filter()
    ).exists()
