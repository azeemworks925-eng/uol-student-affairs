"""
Who may see and act on complaints (DEC-228, DEC-229, DEC-205).

- Students: only complaints they submitted. Their current cohort grants nothing.
- Batch Advisors: complaints whose stored cohort exactly matches one of their assignments
  (batch + semester + section); a partial match grants nothing.
- Super Admins: every complaint, department-wide.

Inactive and anonymous users see nothing. Views must load complaints through
`visible_complaints` / `get_visible_complaint` so a changed ID in a URL cannot reach
another person's record.
"""

from django.http import Http404

from accounts.models import AdvisorAssignment
from accounts.permissions import assigned_cohort_filter

from .models import Complaint


def _active(user):
    return bool(user and user.is_authenticated and user.is_active)


def visible_complaints(user):
    complaints = Complaint.objects.select_related(
        "student", "batch", "semester", "section", "category", "subcategory", "responsible"
    )
    if not _active(user):
        return complaints.none()
    if user.is_super_admin:
        return complaints
    if user.is_batch_advisor:
        return complaints.filter(assigned_cohort_filter(user))
    if user.is_student:
        return complaints.filter(student=user)
    return complaints.none()


def get_visible_complaint(user, reference):
    """The complaint with this reference if the user may see it; otherwise 404, never 403,
    so the response does not reveal whether someone else's complaint exists."""
    try:
        return visible_complaints(user).get(reference=reference)
    except Complaint.DoesNotExist:
        raise Http404("No complaint found.") from None


def advisor_has_cohort(advisor, complaint):
    """Whether the advisor is assigned to the complaint's exact cohort (DEC-205)."""
    return AdvisorAssignment.objects.filter(
        advisor=advisor, batch_id=complaint.batch_id, semester_id=complaint.semester_id, section_id=complaint.section_id
    ).exists()


def can_view_complaint(user, complaint):
    if not _active(user):
        return False
    if user.is_super_admin:
        return True
    if user.is_batch_advisor:
        return advisor_has_cohort(user, complaint)
    if user.is_student:
        return complaint.student_id == user.pk
    return False


def can_manage_complaint(user, complaint):
    """Change status and respond: Batch Advisors of the exact cohort and Super Admins.

    Every advisor assigned to the cohort may act. Limiting actions to the responsible owner
    waits for O27, which decides how that owner is designated.
    """
    if not _active(user):
        return False
    if user.is_super_admin:
        return True
    return user.is_batch_advisor and advisor_has_cohort(user, complaint)


def is_complaint_owner(user, complaint):
    """Student-only actions: further information, "Still not resolved", cancellation request."""
    return _active(user) and user.is_student and complaint.student_id == user.pk
