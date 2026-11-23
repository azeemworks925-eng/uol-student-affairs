"""
Google sign-in end to end: POST to start, Google's redirect back with code and state,
ID token validation by allauth, then the portal's identity rules in the adapter.
Only the HTTP token exchange with Google is stubbed.
"""

import time
from types import SimpleNamespace

from allauth.socialaccount.models import SocialAccount
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.adapters import PortalAccountAdapter, PortalSocialAccountAdapter
from accounts.models import User

from .helpers import (
    ADVISOR_EMAIL,
    GOOGLE_PROVIDERS,
    STUDENT_EMAIL,
    complete_google_sign_in,
    google_claims,
    google_sign_in,
    make_advisor,
    make_student,
    start_google_sign_in,
)


def signed_in_user(client):
    user_id = client.session.get("_auth_user_id")
    return User.objects.get(pk=user_id) if user_id else None


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class StudentGoogleSignInTests(TestCase):
    def test_new_student_is_created_signed_in_and_sent_to_registration(self):
        response = google_sign_in(self.client, google_claims("12345678@Student.UOL.edu.pk", sub="sub-student"))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual(user.email, STUDENT_EMAIL)
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual((user.is_staff, user.is_superuser), (False, False))
        self.assertEqual(signed_in_user(self.client), user)
        self.assertEqual(SocialAccount.objects.get(user=user).uid, "sub-student")
        self.assertRedirects(self.client.get(reverse("home")), reverse("student_register"), target_status_code=200)

    def test_returning_student_signs_in_to_the_same_account(self):
        google_sign_in(self.client, google_claims(STUDENT_EMAIL, sub="sub-student"))
        self.client.logout()

        google_sign_in(self.client, google_claims("12345678@STUDENT.UOL.EDU.PK", sub="sub-student"))

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)
        self.assertEqual(signed_in_user(self.client).email, STUDENT_EMAIL)

    def test_student_created_in_advance_is_linked_on_first_sign_in(self):
        student = make_student()
        google_sign_in(self.client, google_claims(STUDENT_EMAIL, sub="sub-student"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(signed_in_user(self.client), student)

    def test_invalid_student_email_formats_are_refused(self):
        for email in ("ali.khan@student.uol.edu.pk", "1234567@student.uol.edu.pk", "123456789@student.uol.edu.pk"):
            with self.subTest(email=email):
                response = google_sign_in(Client(), google_claims(email, sub=email))
                self.assertEqual(response.status_code, 403)
                self.assertTemplateUsed(response, "accounts/sign_in_denied.html")
        self.assertFalse(User.objects.exists())

    def test_inactive_student_cannot_sign_in(self):
        student = make_student()
        student.is_active = False
        student.save()

        response = google_sign_in(self.client, google_claims(STUDENT_EMAIL))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "deactivated", status_code=403)
        self.assertIsNone(signed_in_user(self.client))


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class StaffGoogleSignInTests(TestCase):
    def test_provisioned_advisor_is_activated_by_first_sign_in(self):
        advisor = make_advisor()

        response = google_sign_in(self.client, google_claims("Advisor@UOL.edu.pk", sub="sub-advisor"))

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(signed_in_user(self.client), advisor)
        self.assertEqual(SocialAccount.objects.get(user=advisor).uid, "sub-advisor")
        self.assertRedirects(self.client.get(reverse("home")), reverse("advisor_home"))

    def test_unprovisioned_staff_email_cannot_self_register(self):
        response = google_sign_in(self.client, google_claims("new.teacher@uol.edu.pk"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "been set up yet. Contact the Super Admin.", status_code=403)
        self.assertFalse(User.objects.exists())
        self.assertIsNone(signed_in_user(self.client))

    @override_settings(UOL_GOOGLE_REQUIRE_HOSTED_DOMAIN=False)
    def test_personal_google_account_is_refused(self):
        response = google_sign_in(self.client, google_claims("someone@gmail.com", hd=None))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class IdentityConsistencyTests(TestCase):
    def test_account_linked_to_one_google_identity_rejects_another(self):
        advisor = make_advisor()
        google_sign_in(self.client, google_claims(ADVISOR_EMAIL, sub="sub-original"))
        self.client.logout()

        response = google_sign_in(self.client, google_claims(ADVISOR_EMAIL, sub="sub-impostor"))

        self.assertEqual(response.status_code, 403)
        self.assertIsNone(signed_in_user(self.client))
        self.assertEqual(list(SocialAccount.objects.filter(user=advisor).values_list("uid", flat=True)), ["sub-original"])

    def test_changed_google_email_is_refused(self):
        google_sign_in(self.client, google_claims(STUDENT_EMAIL, sub="sub-student"))
        self.client.logout()

        response = google_sign_in(self.client, google_claims("87654321@student.uol.edu.pk", sub="sub-student"))

        self.assertEqual(response.status_code, 403)
        self.assertIsNone(signed_in_user(self.client))
        self.assertEqual(User.objects.count(), 1)


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class ClaimValidationTests(TestCase):
    def assert_refused(self, claims, status=403):
        response = google_sign_in(self.client, claims)
        if status is not None:
            self.assertEqual(response.status_code, status)
        self.assertIsNone(signed_in_user(self.client))
        self.assertFalse(User.objects.exists())
        return response

    def test_unverified_email_is_refused(self):
        self.assert_refused(google_claims(STUDENT_EMAIL, email_verified=False))

    def test_missing_email_is_refused(self):
        claims = google_claims(STUDENT_EMAIL)
        del claims["email"]
        self.assert_refused(claims)

    def test_missing_hosted_domain_is_refused_by_default(self):
        self.assert_refused(google_claims(STUDENT_EMAIL, hd=None))

    def test_foreign_hosted_domain_is_refused(self):
        self.assert_refused(google_claims(STUDENT_EMAIL, hd="example.com"))

    @override_settings(UOL_GOOGLE_REQUIRE_HOSTED_DOMAIN=False)
    def test_hosted_domain_check_can_be_disabled_by_configuration(self):
        google_sign_in(self.client, google_claims(STUDENT_EMAIL, hd=None))
        self.assertEqual(signed_in_user(self.client).email, STUDENT_EMAIL)

    def test_token_for_another_client_is_refused(self):
        response = self.assert_refused(google_claims(STUDENT_EMAIL, aud="someone-else"), status=None)
        self.assertTemplateUsed(response, "socialaccount/authentication_error.html")

    def test_token_from_another_issuer_is_refused(self):
        response = self.assert_refused(google_claims(STUDENT_EMAIL, iss="https://evil.example.com"), status=None)
        self.assertTemplateUsed(response, "socialaccount/authentication_error.html")

    def test_expired_token_is_refused(self):
        past = int(time.time()) - 7200
        response = self.assert_refused(google_claims(STUDENT_EMAIL, iat=past, exp=past + 60), status=None)
        self.assertTemplateUsed(response, "socialaccount/authentication_error.html")

    def test_forged_state_is_refused(self):
        start_google_sign_in(self.client)
        response = complete_google_sign_in(self.client, google_claims(STUDENT_EMAIL), "forged-state")
        self.assertTemplateUsed(response, "socialaccount/authentication_error.html")
        self.assertIsNone(signed_in_user(self.client))

    def test_callback_without_started_sign_in_is_refused(self):
        response = complete_google_sign_in(self.client, google_claims(STUDENT_EMAIL), "never-issued")
        self.assertTemplateUsed(response, "socialaccount/authentication_error.html")
        self.assertFalse(User.objects.exists())


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class SignInEndpointTests(TestCase):
    def test_login_page_offers_google_sign_in(self):
        response = self.client.get(reverse("account_login"))
        self.assertContains(response, "Sign in with Google")
        self.assertContains(response, reverse("google_login"))

    def test_sign_in_must_start_with_a_post(self):
        response = self.client.get(reverse("google_login"))
        self.assertEqual(response.status_code, 200)  # Confirmation page, no redirect to Google.
        self.assertFalse(response.has_header("Location"))

    def test_sign_in_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("google_login")).status_code, 403)

    def test_starting_sign_in_requests_pkce_and_openid_scopes(self):
        response = self.client.post(reverse("google_login"))
        self.assertIn("code_challenge=", response["Location"])
        self.assertIn("openid", response["Location"])

    def test_password_login_and_signup_are_disabled(self):
        response = self.client.post(reverse("account_login"), {"login": STUDENT_EMAIL, "password": "x"})
        self.assertEqual(response.status_code, 403)
        for name in ("account_signup", "account_reset_password", "account_change_password"):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_logout_requires_post(self):
        make_student()
        self.client.force_login(User.objects.get())
        self.client.get(reverse("account_logout"))
        self.assertIsNotNone(signed_in_user(self.client))
        self.client.post(reverse("account_logout"))
        self.assertIsNone(signed_in_user(self.client))


class SignupGuardTests(TestCase):
    """is_open_for_signup is a second guard behind pre_social_login: only students may sign up."""

    def test_signup_is_open_only_to_valid_student_emails(self):
        adapter = PortalSocialAccountAdapter()
        for email, expected in (
            (STUDENT_EMAIL, True),
            (ADVISOR_EMAIL, False),
            ("ali.khan@student.uol.edu.pk", False),
            ("someone@gmail.com", False),
            ("", False),
        ):
            with self.subTest(email=email):
                login = SimpleNamespace(user=User(email=email))
                self.assertIs(adapter.is_open_for_signup(None, login), expected)

    def test_local_password_signup_is_closed(self):
        self.assertFalse(PortalAccountAdapter().is_open_for_signup(None))


@override_settings(SOCIALACCOUNT_PROVIDERS={"google": {"SCOPE": ["openid", "email", "profile"]}})
class GoogleNotConfiguredTests(TestCase):
    def test_login_page_explains_google_is_not_configured(self):
        response = self.client.get(reverse("account_login"))
        self.assertContains(response, "not configured")
        self.assertNotContains(response, "Sign in with Google")
