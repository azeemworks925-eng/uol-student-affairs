"""
Server-side access control.

Access is decided only from the authenticated user's stored role and assignments, never
from URL or request parameters. Later modules should combine `role_required` (who may
open a view) with the scoping helpers (which records they may see).
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import AdvisorAssignment, StudentProfile, User


def role_required(*roles):
    """Allow only authenticated, active users whose stored role is one of `roles`."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


student_required = role_required(User.Role.STUDENT)
batch_advisor_required = role_required(User.Role.BATCH_ADVISOR)
super_admin_required = role_required(User.Role.SUPER_ADMIN)


def _assignment_filter(user, prefix=""):
    """Q object matching records in any (semester, section) assigned to the advisor."""
    pairs = AdvisorAssignment.objects.filter(advisor=user).values_list("semester_id", "section_id")
    query = Q(pk__in=[])  # Matches nothing when there are no assignments.
    for semester_id, section_id in pairs:
        query |= Q(**{f"{prefix}semester_id": semester_id, f"{prefix}section_id": section_id})
    return query


def can_access_section(user, semester, section):
    """Whether the user may see data for this semester and section (DEC-015, DEC-229)."""
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_super_admin:
        return True
    if user.is_batch_advisor:
        return AdvisorAssignment.objects.filter(advisor=user, semester=semester, section=section).exists()
    if user.is_student:
        profile = getattr(user, "student_profile", None)
        return profile is not None and (profile.semester_id, profile.section_id) == (semester.pk, section.pk)
    return False


def visible_student_profiles(user):
    """Student profiles the user may see: all, their assigned sections, or only their own."""
    profiles = StudentProfile.objects.select_related("user", "batch", "semester", "section")
    if not (user.is_authenticated and user.is_active):
        return profiles.none()
    if user.is_super_admin:
        return profiles
    if user.is_batch_advisor:
        return profiles.filter(_assignment_filter(user))
    if user.is_student:
        return profiles.filter(user=user)
    return profiles.none()
