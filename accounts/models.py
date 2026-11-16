from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from . import identity


class PortalUserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """
        Lowercase the entire address, since the email is the portal's account identity.

        Django's default lowercases only the domain. AbstractUser.clean() calls this
        method too, so model validation and the admin forms follow the same rule.
        """
        return identity.normalize_email(email)

    def get_by_natural_key(self, username):
        # Authentication lookups use the same rule as account creation.
        return super().get_by_natural_key(self.normalize_email(username))

    async def aget_by_natural_key(self, username):
        # Django's async version queries directly rather than calling get_by_natural_key().
        return await super().aget_by_natural_key(self.normalize_email(username))

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        if not email:
            raise ValueError("An email address is required.")

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        # Validate email format, role, the role's email rule and uniqueness (review M2).
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        role = extra_fields.setdefault("role", User.Role.SUPER_ADMIN)
        if role != User.Role.SUPER_ADMIN:
            raise ValueError("A superuser must have the Super Admin role.")

        # The flags are derived from the role on save (review M1); explicit
        # contradicting values are rejected rather than silently overridden.
        if extra_fields.pop("is_staff", True) is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.pop("is_superuser", True) is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        BATCH_ADVISOR = "batch_advisor", "Batch Advisor"
        SUPER_ADMIN = "super_admin", "Super Admin"

    STAFF_ROLES = (Role.BATCH_ADVISOR, Role.SUPER_ADMIN)

    username = None
    email = models.EmailField(unique=True)
    # DEC-201 collects a full name. AbstractUser's first_name/last_name are kept for
    # compatibility but are not used by the portal.
    full_name = models.CharField(max_length=150, blank=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )

    objects = PortalUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()  # Normalizes the email through PortalUserManager.normalize_email.
        if not self.email or self.role not in self.Role.values:
            return  # Field validation reports these.
        if self.role == self.Role.STUDENT and not identity.is_student_email(self.email):
            raise ValidationError(
                {"email": "Student accounts must use an eight-digit SAP ID email address "
                          f"at @{identity.STUDENT_EMAIL_DOMAIN}."}
            )
        if self.role in self.STAFF_ROLES and not identity.is_staff_email(self.email):
            domains = ", ".join(sorted(identity.staff_email_domains())) or "(none configured)"
            raise ValidationError(
                {"email": f"Staff accounts must use an official UOL staff email address ({domains})."}
            )

    def save(self, *args, **kwargs):
        # Review M1: the role is the single source of truth. Only the Super Admin can
        # use the Django admin, and no other role can hold admin flags.
        is_super_admin = self.role == self.Role.SUPER_ADMIN
        self.is_staff = is_super_admin
        self.is_superuser = is_super_admin
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        return self.get_full_name()

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_batch_advisor(self):
        return self.role == self.Role.BATCH_ADVISOR

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN


class StudentProfile(models.Model):
    """Registration details a student declares after their first Google sign-in (DEC-201)."""

    DEFAULT_DEPARTMENT = "Software Engineering"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="student_profile",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    # Extracted from the verified student email, never typed by the student (DEC-011).
    sap_id = models.CharField("SAP ID", max_length=8, unique=True, editable=False)
    department = models.CharField(max_length=100, default=DEFAULT_DEPARTMENT, editable=False)
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="students")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="students")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="students")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sap_id"]

    def __str__(self):
        return f"{self.sap_id} ({self.user.get_full_name()})"

    def clean(self):
        if self.user_id and not self.user.is_student:
            raise ValidationError({"user": "Only student accounts can have a student profile."})

    def save(self, *args, **kwargs):
        self.sap_id = identity.extract_sap_id(self.user.email)
        if not self.sap_id:
            raise ValidationError("A student profile requires a valid student email address.")
        super().save(*args, **kwargs)


class AdvisorAssignment(models.Model):
    """
    Assigns a Batch Advisor to one cohort: the exact batch + semester + section combination
    (DEC-205; see also DEC-013, DEC-015, DEC-204).

    Several advisors may share a cohort, and one advisor may hold several cohorts.
    Assignments are changed by adding or removing rows.
    """

    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="advisor_assignments",
        limit_choices_to={"role": User.Role.BATCH_ADVISOR},
    )
    batch = models.ForeignKey("academics.Batch", on_delete=models.PROTECT, related_name="advisor_assignments")
    semester = models.ForeignKey("academics.Semester", on_delete=models.PROTECT, related_name="advisor_assignments")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="advisor_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch__name", "semester__number", "section__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["advisor", "batch", "semester", "section"], name="unique_advisor_cohort_assignment"
            )
        ]

    def __str__(self):
        return f"{self.advisor} - {self.batch}, {self.semester}, {self.section}"

    def clean(self):
        if self.advisor_id and not self.advisor.is_batch_advisor:
            raise ValidationError({"advisor": "Only Batch Advisor accounts can be assigned to sections."})


class StudentProfileChange(models.Model):
    """Audit record of a change to a student's profile details (DEC-211)."""

    profile = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="changes")
    field_name = models.CharField(max_length=50)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.profile.sap_id}: {self.field_name} changed"
