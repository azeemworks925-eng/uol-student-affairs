from django.contrib import admin
from django.contrib.auth import aauthenticate, authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import User

PASSWORD = "Str0ng-test-pass!"


class UserModelTests(TestCase):
    def test_auth_user_model_is_custom_user(self):
        self.assertIs(get_user_model(), User)

    def test_email_is_the_login_identifier(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, [])
        self.assertFalse(any(f.name == "username" for f in User._meta.get_fields()))

    def test_str_returns_email(self):
        user = User.objects.create_user(email="12345678@student.uol.edu.pk")
        self.assertEqual(str(user), "12345678@student.uol.edu.pk")

    def test_email_must_be_unique(self):
        User.objects.create_user(email="12345678@student.uol.edu.pk")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="12345678@student.uol.edu.pk")


class CreateUserTests(TestCase):
    def test_creates_user_with_email_and_hashed_password(self):
        user = User.objects.create_user(email="12345678@student.uol.edu.pk", password=PASSWORD)

        self.assertEqual(user.email, "12345678@student.uol.edu.pk")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_defaults_to_active_non_staff_student(self):
        user = User.objects.create_user(email="12345678@student.uol.edu.pk")

        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_without_password_sets_unusable_password(self):
        user = User.objects.create_user(email="12345678@student.uol.edu.pk")
        self.assertFalse(user.has_usable_password())

    def test_requires_email(self):
        for missing in (None, "", "   "):
            with self.subTest(email=missing), self.assertRaisesMessage(
                ValueError, "An email address is required."
            ):
                User.objects.create_user(email=missing, password=PASSWORD)

    def test_accepts_explicit_role(self):
        user = User.objects.create_user(
            email="advisor@uol.edu.pk", role=User.Role.BATCH_ADVISOR
        )
        self.assertEqual(user.role, User.Role.BATCH_ADVISOR)
        self.assertFalse(user.is_staff)


class CreateSuperuserTests(TestCase):
    def test_creates_super_admin_with_staff_and_superuser_flags(self):
        user = User.objects.create_superuser(email="admin@uol.edu.pk", password=PASSWORD)

        self.assertEqual(user.role, User.Role.SUPER_ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))

    def test_rejects_is_staff_false(self):
        with self.assertRaisesMessage(ValueError, "is_staff=True"):
            User.objects.create_superuser(
                email="admin@uol.edu.pk", password=PASSWORD, is_staff=False
            )

    def test_rejects_is_superuser_false(self):
        with self.assertRaisesMessage(ValueError, "is_superuser=True"):
            User.objects.create_superuser(
                email="admin@uol.edu.pk", password=PASSWORD, is_superuser=False
            )

    def test_requires_email(self):
        with self.assertRaisesMessage(ValueError, "An email address is required."):
            User.objects.create_superuser(email="", password=PASSWORD)


class EmailNormalizationTests(TestCase):
    """Emails are lowercased in full on every path, independent of database collation."""

    MIXED = "Ali.Khan@Student.UOL.edu.pk"
    NORMALIZED = "ali.khan@student.uol.edu.pk"

    def test_normalize_email_lowercases_whole_address_and_strips(self):
        for raw in (
            self.MIXED,
            "ALI.KHAN@STUDENT.UOL.EDU.PK",
            f"  {self.MIXED}  ",
            self.NORMALIZED,
        ):
            with self.subTest(raw=raw):
                self.assertEqual(User.objects.normalize_email(raw), self.NORMALIZED)

    def test_create_user_stores_lowercase_email(self):
        user = User.objects.create_user(email=self.MIXED)
        user.refresh_from_db()
        self.assertEqual(user.email, self.NORMALIZED)

    def test_create_superuser_stores_lowercase_email(self):
        user = User.objects.create_superuser(email="ADMIN@UOL.EDU.PK", password=PASSWORD)
        user.refresh_from_db()
        self.assertEqual(user.email, "admin@uol.edu.pk")

    def test_create_user_rejects_case_variant_of_existing_email(self):
        User.objects.create_user(email=self.NORMALIZED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email=self.MIXED)

    def test_model_clean_lowercases_email(self):
        user = User(email=self.MIXED)
        user.clean()
        self.assertEqual(user.email, self.NORMALIZED)

    def test_full_clean_rejects_case_variant_of_existing_email(self):
        User.objects.create_user(email=self.NORMALIZED)
        user = User(email=self.MIXED)
        user.set_unusable_password()

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn("email", ctx.exception.message_dict)

    def test_full_clean_still_rejects_invalid_email(self):
        user = User(email="Not-An-Email")
        user.set_unusable_password()

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn("email", ctx.exception.message_dict)

    def test_authentication_lookup_ignores_case(self):
        User.objects.create_user(email=self.NORMALIZED, password=PASSWORD)

        self.assertEqual(User.objects.get_by_natural_key(self.MIXED).email, self.NORMALIZED)
        self.assertIsNotNone(authenticate(email=self.MIXED, password=PASSWORD))


class AsyncEmailLookupTests(TestCase):
    MIXED = "Ali.Khan@Student.UOL.edu.pk"
    NORMALIZED = "ali.khan@student.uol.edu.pk"

    @classmethod
    def setUpTestData(cls):
        User.objects.create_user(email=cls.NORMALIZED, password=PASSWORD)

    async def test_async_lookup_ignores_case(self):
        user = await User.objects.aget_by_natural_key(self.MIXED)
        self.assertEqual(user.email, self.NORMALIZED)

    async def test_async_authentication_ignores_case(self):
        user = await aauthenticate(email=self.MIXED, password=PASSWORD)
        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.NORMALIZED)


class UserAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(email="admin@uol.edu.pk", password=PASSWORD)
        cls.student = User.objects.create_user(email="12345678@student.uol.edu.pk")

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_user_model_is_registered(self):
        self.assertTrue(admin.site.is_registered(User))

    def test_changelist_loads_and_searches_by_email(self):
        url = reverse("admin:accounts_user_changelist")

        response = self.client.get(url, {"q": "12345678"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "12345678@student.uol.edu.pk")
        self.assertNotContains(response, "admin@uol.edu.pk</a>")

    def test_changelist_filters_by_role(self):
        url = reverse("admin:accounts_user_changelist")

        response = self.client.get(url, {"role__exact": User.Role.SUPER_ADMIN})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin@uol.edu.pk")
        self.assertNotContains(response, "12345678@student.uol.edu.pk")

    def test_change_page_loads(self):
        url = reverse("admin:accounts_user_change", args=[self.student.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_add_user_with_email_and_role(self):
        url = reverse("admin:accounts_user_add")
        self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(
            url,
            {
                "email": "advisor@uol.edu.pk",
                "role": User.Role.BATCH_ADVISOR,
                "usable_password": "false",
            },
        )

        self.assertEqual(response.status_code, 302)
        advisor = User.objects.get(email="advisor@uol.edu.pk")
        self.assertEqual(advisor.role, User.Role.BATCH_ADVISOR)
        self.assertFalse(advisor.has_usable_password())

    def _add_user(self, email):
        return self.client.post(
            reverse("admin:accounts_user_add"),
            {"email": email, "role": User.Role.BATCH_ADVISOR, "usable_password": "false"},
        )

    def test_add_user_lowercases_mixed_case_email(self):
        response = self._add_user("Teacher.Name@UOL.EDU.PK")

        self.assertEqual(response.status_code, 302)
        # Select the new user by excluding known rows, not by email: a case-insensitive
        # collation (MySQL utf8mb4_0900_ai_ci) would match either case in a filter.
        created = User.objects.exclude(pk__in=[self.superuser.pk, self.student.pk]).get()
        self.assertEqual(created.email, "teacher.name@uol.edu.pk")

    def test_add_user_rejects_case_variant_of_existing_email(self):
        response = self._add_user("12345678@STUDENT.UOL.EDU.PK")

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["adminform"].form.errors)
        self.assertEqual(User.objects.count(), 2)

    def test_add_user_rejects_invalid_email(self):
        response = self._add_user("Not-An-Email")

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["adminform"].form.errors)

    def test_change_user_lowercases_mixed_case_email(self):
        response = self.client.post(
            reverse("admin:accounts_user_change", args=[self.student.pk]),
            {"email": "87654321@Student.UOL.edu.pk", "role": User.Role.STUDENT, "is_active": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "87654321@student.uol.edu.pk")
