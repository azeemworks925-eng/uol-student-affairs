"""Account operations shared by views, the admin and management commands.

The lifecycle services (`set_account_active`, `update_student_profile`) and registration keep
DEC-016/DEC-323 (no vacant CR/GR post in a represented, eligible cohort) by taking the cohort
lock and calling accounts.representation in the same transaction as the account or profile
change. Every caller (the admin now, portal pages later) must use them.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CohortRepresentation, StudentProfile, StudentProfileChange, User
from .representation import (  # noqa: F401  (the representation operations are part of this API)
    DETAILS_CHANGED,
    Cohort,
    appoint_representatives,
    cohort_is_active,
    current_post_of,
    lock_current_periods,
    lock_sections,
    lock_users,
    replace_representatives,
    resolve_departure,
    swap_representatives,
)

LAST_SUPER_ADMIN = "The last active Super Admin cannot be deactivated."
INACTIVE_TARGET = "Choose an active batch, semester and section."
PROFILE_FIELDS = ("batch", "semester", "section")


class BootstrapError(Exception):
    pass


@transaction.atomic
def register_student(user, *, full_name, batch, semester, section):
    """Complete a student's one-time registration after their first Google sign-in."""
    if not user.is_student:
        raise ValueError("Only student accounts can register a student profile.")
    if StudentProfile.objects.filter(user=user).exists():
        raise ValueError("This student has already registered.")
    # The cohort lock (spec 5.7): registration changes the cohort's membership, so it is
    # serialised with appointments, departures and academic deactivations of this cohort.
    cohort = Cohort(batch.pk, semester.pk, section.pk)
    lock_sections([cohort.section_id])
    if not cohort_is_active(cohort):
        raise ValidationError(INACTIVE_TARGET)
    user.full_name = full_name.strip()
    user.full_clean()
    user.save(update_fields=["full_name"])
    profile = StudentProfile(user=user, batch=batch, semester=semester, section=section)
    profile.full_clean(exclude=["sap_id"])
    profile.save()
    return profile


def record_profile_changes(profile, changes, changed_by):
    """
    Audit changes to a student's details (DEC-211).

    `changes` maps a field name to an (old_value, new_value) pair.
    """
    StudentProfileChange.objects.bulk_create(
        StudentProfileChange(
            profile=profile,
            field_name=field,
            old_value=str(old if old is not None else "")[:255],
            new_value=str(new if new is not None else "")[:255],
            changed_by=changed_by,
        )
        for field, (old, new) in changes.items()
        if old != new
    )


@transaction.atomic
def bootstrap_super_admin(*, email, full_name):
    """
    Create the initial Super Admin (DEC-203).

    Runs only from the server shell (manage.py bootstrap_super_admin), refuses to run
    once a Super Admin exists, and sets no password: the account signs in with Google.
    """
    if User.objects.filter(role=User.Role.SUPER_ADMIN).exists():
        raise BootstrapError("A Super Admin already exists. Bootstrap can only create the first one.")
    email = User.objects.normalize_email(email)
    if User.objects.filter(email=email).exists():
        raise BootstrapError(f"An account already exists for {email}.")
    return User.objects.create_superuser(email=email, password=None, full_name=full_name.strip())


# ---------------------------------------------------------------------------------------------
# Lifecycle (COLLECTIVE_ISSUES_SPEC.md section 5.4; DEC-212, DEC-323)
# ---------------------------------------------------------------------------------------------

@transaction.atomic
def set_account_active(user, active, *, actor, replacement=None):
    """Activate or deactivate an account in one transaction.

    Deactivating a CR or GR of an active, represented cohort needs `replacement` (appointed in the
    same transaction), or is refused, unless fewer than two active students would remain, in which
    case the cohort's representation closes (DEC-323). In an inactive cohort the period simply
    ends. Reactivation never restores a post. The last active Super Admin can't be deactivated.
    """
    uid = user.pk
    profile_section = StudentProfile.objects.filter(user_id=uid).values_list("section_id", flat=True).first()
    held = current_post_of(uid)
    sections = {profile_section, held.section_id if held else None}
    lock_sections(sections)
    # Re-read under the cohort locks; refuse rather than act on a cohort that just changed.
    held = current_post_of(uid)
    if StudentProfile.objects.filter(user_id=uid).values_list("section_id", flat=True).first() != profile_section or (
            held is not None and held.section_id not in sections):
        raise ValidationError(DETAILS_CHANGED)
    if held is not None:
        held = lock_current_periods([held.pk]).get(held.pk)
    deactivating_admin = not active and user.role == User.Role.SUPER_ADMIN
    admin_ids = (list(User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).values_list("pk", flat=True))
                 if deactivating_admin else [])
    users = lock_users([uid, replacement.pk if replacement is not None else None, *admin_ids])
    current = users[uid]
    if deactivating_admin and current.is_active and not User.objects.filter(
            role=User.Role.SUPER_ADMIN, is_active=True).exclude(pk=uid).exists():
        raise ValidationError({"is_active": LAST_SUPER_ADMIN})
    if replacement is not None and (active or held is None):
        raise ValidationError({"replacement": "A replacement is only needed when deactivating a CR or GR."})
    if not active and current.is_active and held is not None:
        resolve_departure(current, held, actor=actor,
                          replacement=users.get(replacement.pk) if replacement is not None else None,
                          inactive_reason=CohortRepresentation.EndReason.STUDENT_DEACTIVATED)
    if current.is_active != active:
        current.is_active = active
        current.save(update_fields=["is_active"])
    user.is_active = active
    return current


@transaction.atomic
def update_student_profile(profile, changes, *, actor, replacement=None):
    """Change a student's batch, semester or section, audit it, and keep DEC-323, in one
    transaction. A CR or GR leaving an active, represented cohort needs `replacement`, or the
    change is refused, unless fewer than two active students would remain (closure). The new
    cohort must be active (spec 5.7). Students arriving in a cohort never change its posts."""
    unknown = set(changes) - set(PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported profile fields: {sorted(unknown)}")
    before = StudentProfile.objects.filter(pk=profile.pk).values_list(
        "batch_id", "semester_id", "section_id", "user_id").get()
    old, uid = Cohort(*before[:3]), before[3]
    new = Cohort(
        changes["batch"].pk if "batch" in changes else old.batch_id,
        changes["semester"].pk if "semester" in changes else old.semester_id,
        changes["section"].pk if "section" in changes else old.section_id,
    )
    held = current_post_of(uid)
    sections = {old.section_id, new.section_id, held.section_id if held else None}
    lock_sections(sections)
    held = current_post_of(uid)
    if held is not None and held.section_id not in sections:
        raise ValidationError(DETAILS_CHANGED)
    if held is not None:
        held = lock_current_periods([held.pk]).get(held.pk)
    users = lock_users([uid, replacement.pk if replacement is not None else None])
    fresh = StudentProfile.objects.select_for_update().select_related("batch", "semester", "section").get(pk=profile.pk)
    if Cohort.of(fresh) != old:
        raise ValidationError(DETAILS_CHANGED)
    moving = new != old
    if moving and not cohort_is_active(new):
        raise ValidationError(INACTIVE_TARGET)
    if replacement is not None and not (moving and held is not None):
        raise ValidationError({"replacement": "A replacement is only needed when a CR or GR moves out of their cohort."})
    if moving and held is not None and users[uid].is_active:
        resolve_departure(users[uid], held, actor=actor,
                          replacement=users.get(replacement.pk) if replacement is not None else None,
                          inactive_reason=CohortRepresentation.EndReason.COHORT_CHANGED)
    previous = {field: getattr(fresh, field) for field in changes}
    for field, value in changes.items():
        setattr(fresh, field, value)
        setattr(profile, field, value)
    fresh.save()
    record_profile_changes(fresh, {field: (previous[field], value) for field, value in changes.items()}, actor)
    return fresh
