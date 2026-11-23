"""
Who may see and act on meetings (DEC-246, DEC-261, DEC-262, DEC-328).

- Student (including a CR or GR): only their own meetings.
- Batch Advisor: meetings whose stored cohort exactly matches one of their assignments.
- Super Admin: every meeting, read-only.

Views load records through `get_visible_meeting`, so a changed ID in a URL gives a 404.
"""

from django.http import Http404

from accounts.models import AdvisorAssignment
from accounts.permissions import assigned_cohort_filter

from .models import Meeting


def _active(user):
    return bool(user and user.is_authenticated and user.is_active)


def visible_meetings(user):
    meetings = Meeting.objects.select_related(
        "student", "student__student_profile", "advisor", "batch", "semester", "section"
    )
    if not _active(user):
        return meetings.none()
    if user.is_super_admin:
        return meetings
    if user.is_batch_advisor:
        return meetings.filter(assigned_cohort_filter(user))
    if user.is_student:
        return meetings.filter(student=user)
    return meetings.none()


def get_visible_meeting(user, pk):
    """The meeting if the user may see it; otherwise 404, never 403, so the response does not
    reveal whether someone else's meeting exists."""
    try:
        return visible_meetings(user).get(pk=pk)
    except Meeting.DoesNotExist:
        raise Http404("No meeting found.") from None


def advisor_can_act(user, meeting):
    """Every active advisor assigned to the meeting's exact cohort can act on it."""
    return _active(user) and user.is_batch_advisor and AdvisorAssignment.objects.filter(
        advisor=user,
        batch_id=meeting.batch_id,
        semester_id=meeting.semester_id,
        section_id=meeting.section_id,
    ).exists()


def is_own_meeting(user, meeting):
    return _active(user) and user.is_student and meeting.student_id == user.pk
