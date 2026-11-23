"""
Who may see and act on Student Voice submissions (DEC-253, DEC-254, DEC-326).

- Student (including a CR or GR): only their own submissions.
- Batch Advisor: submissions whose stored cohort exactly matches one of their assignments.
- Super Admin: every submission, read-only.

Views load records through `get_visible_submission`, so a changed ID in a URL gives a 404.
"""

from django.http import Http404

from accounts.models import AdvisorAssignment
from accounts.permissions import assigned_cohort_filter

from .models import Submission


def _active(user):
    return bool(user and user.is_authenticated and user.is_active)


def visible_submissions(user):
    submissions = Submission.objects.select_related(
        "student", "student__student_profile", "batch", "semester", "section", "answered_by", "reviewed_by"
    )
    if not _active(user):
        return submissions.none()
    if user.is_super_admin:
        return submissions
    if user.is_batch_advisor:
        return submissions.filter(assigned_cohort_filter(user))
    if user.is_student:
        return submissions.filter(student=user)
    return submissions.none()


def get_visible_submission(user, pk):
    """The submission if the user may see it; otherwise 404, never 403, so the response does not
    reveal whether someone else's submission exists."""
    try:
        return visible_submissions(user).get(pk=pk)
    except Submission.DoesNotExist:
        raise Http404("No submission found.") from None


def can_act(user, submission):
    """Answer, reply or mark reviewed: every active advisor of the exact cohort (DEC-326)."""
    return _active(user) and user.is_batch_advisor and AdvisorAssignment.objects.filter(
        advisor=user,
        batch_id=submission.batch_id,
        semester_id=submission.semester_id,
        section_id=submission.section_id,
    ).exists()
