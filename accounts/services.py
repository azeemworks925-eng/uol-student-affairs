"""Account operations shared by views, the admin and management commands."""

from django.db import transaction

from .models import StudentProfile, StudentProfileChange, User


class BootstrapError(Exception):
    pass


@transaction.atomic
def register_student(user, *, full_name, batch, semester, section):
    """Complete a student's one-time registration after their first Google sign-in."""
    if not user.is_student:
        raise ValueError("Only student accounts can register a student profile.")
    if StudentProfile.objects.filter(user=user).exists():
        raise ValueError("This student has already registered.")
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
