
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class PortalUserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """
        Lowercase the entire address, since the email is the portal's account identity.

        Django's default lowercases only the domain. AbstractUser.clean() calls this
        method too, so model validation and the admin forms follow the same rule.
        """
        return (email or "").strip().lower()

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
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "super_admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        BATCH_ADVISOR = "batch_advisor", "Batch Advisor"
        SUPER_ADMIN = "super_admin", "Super Admin"

    username = None
    email = models.EmailField(unique=True)

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
