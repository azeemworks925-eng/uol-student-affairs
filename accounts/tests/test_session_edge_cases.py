"""Authenticated-session edge cases in registration, deactivation and Super Admin provisioning."""

from unittest import mock

from allauth.socialaccount.models import SocialAccount
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import StudentProfile, User

from .helpers import (
    GOOGLE_PROVIDERS,
    STUDENT_EMAIL,
    SUPER_ADMIN_EMAIL,
    google_claims,
    google_sign_in,
    make_academics,
    make_student,
    make_super_admin,
)


def signed_in(client):
    return "_auth_user_id" in client.session


def registration_data(academics):
    return {
        "full_name": "Ali Khan",
        "batch": academics["batch"].pk,
        "semester": academics["semester"].pk,
        "section": academics["section"].pk,
    }


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class DeactivationDuringSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()

    def test_google_session_ends_when_account_is_deactivated(self):
        # Signed in through the real Google flow, so the allauth backend is the session's backend.
        google_sign_in(self.client, google_claims(STUDENT_EMAIL))
        self.client.post(reverse("student_register"), registration_data(self.academics))
        self.assertEqual(self.client.get(reverse("student_home")).status_code, 200)

        User.objects.filter(email=STUDENT_EMAIL).update(is_active=False)

        response = self.client.get(reverse("student_home"))
        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_student_deactivated_mid_registration_cannot_complete_it(self):
        google_sign_in(self.client, google_claims(STUDENT_EMAIL))
        User.objects.filter(email=STUDENT_EMAIL).update(is_active=False)

        response = self.client.post(reverse("student_register"), registration_data(self.academics))

        self.assertTrue(response["Location"].startswith(reverse("account_login")))
        self.assertFalse(StudentProfile.objects.exists())

    def test_reactivated_student_can_sign_in_again(self):
        google_sign_in(self.client, google_claims(STUDENT_EMAIL))
        User.objects.filter(email=STUDENT_EMAIL).update(is_active=False)
        self.client.logout()
        User.objects.filter(email=STUDENT_EMAIL).update(is_active=True)

        google_sign_in(self.client, google_claims(STUDENT_EMAIL))

        self.assertTrue(signed_in(self.client))
        self.assertEqual(SocialAccount.objects.count(), 1)


class RegistrationRaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()

    def test_concurrent_duplicate_registration_does_not_error(self):
        # A second submission racing the first passes the "already registered" check, then
        # hits the database's one-profile-per-user constraint.
        student = make_student(full_name="")
        self.client.force_login(student)

        with mock.patch("accounts.views.register_student", side_effect=IntegrityError):
            response = self.client.post(reverse("student_register"), registration_data(self.academics))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)


class MultipleSuperAdminTests(TestCase):
    """After bootstrap, further Super Admins are provisioned by an existing Super Admin."""

    def setUp(self):
        self.head = make_super_admin()
        self.client.force_login(self.head)

    def add_super_admin(self, email="deputy@uol.edu.pk"):
        return self.client.post(
            reverse("admin:accounts_user_add"),
            {"email": email, "full_name": "Deputy Head", "role": User.Role.SUPER_ADMIN},
        )

    def deactivate(self, user):
        return self.client.post(reverse("admin:accounts_user_change", args=[user.pk]), {"full_name": user.full_name})

    def test_super_admin_provisions_another_super_admin_without_password(self):
        response = self.add_super_admin("Deputy@UOL.edu.pk")

        self.assertEqual(response.status_code, 302)
        deputy = User.objects.get(email="deputy@uol.edu.pk")
        self.assertEqual(deputy.role, User.Role.SUPER_ADMIN)
        self.assertEqual((deputy.is_staff, deputy.is_superuser, deputy.is_active), (True, True, True))
        self.assertFalse(deputy.has_usable_password())

    def test_additional_super_admin_requires_staff_email(self):
        for email in (STUDENT_EMAIL, "deputy@gmail.com"):
            with self.subTest(email=email):
                response = self.add_super_admin(email)
                self.assertIn("email", response.context["adminform"].form.errors)
        self.assertEqual(User.objects.filter(role=User.Role.SUPER_ADMIN).count(), 1)

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
    def test_additional_super_admin_is_activated_by_google_and_can_manage(self):
        self.add_super_admin()
        self.client.logout()

        google_sign_in(self.client, google_claims("deputy@uol.edu.pk", sub="sub-deputy"))

        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("super_admin_home")).status_code, 200)

    def test_bootstrap_still_refuses_once_any_super_admin_exists(self):
        with self.assertRaisesMessage(CommandError, "already exists"):
            call_command("bootstrap_super_admin", email="other@uol.edu.pk", full_name="Other")

    def test_a_super_admin_can_be_deactivated_while_another_remains_active(self):
        self.add_super_admin()
        deputy = User.objects.get(email="deputy@uol.edu.pk")

        response = self.deactivate(deputy)

        self.assertEqual(response.status_code, 302)
        deputy.refresh_from_db()
        self.assertFalse(deputy.is_active)

    def test_the_last_active_super_admin_cannot_be_deactivated(self):
        response = self.deactivate(self.head)

        self.assertEqual(response.status_code, 200)
        self.assertIn("is_active", response.context["adminform"].form.errors)
        self.head.refresh_from_db()
        self.assertTrue(self.head.is_active)

    def test_last_active_check_ignores_inactive_super_admins(self):
        self.add_super_admin()
        User.objects.filter(email="deputy@uol.edu.pk").update(is_active=False)

        response = self.deactivate(self.head)

        self.assertEqual(response.status_code, 200)
        self.head.refresh_from_db()
        self.assertTrue(self.head.is_active)
