"""Sign-in, finished (DEC-327): idle timeout, messages, return path, refusals and demo staff.
Every address here is made up."""

from datetime import timedelta
from io import StringIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from accounts import identity
from accounts.adapters import DENIAL_MESSAGES, PortalAccountAdapter
from accounts.middleware import SESSION_MARKER_COOKIE
from accounts.models import AdvisorAssignment, User

from .helpers import (
    ADVISOR_EMAIL,
    GOOGLE_PROVIDERS,
    STUDENT_EMAIL,
    cohort,
    google_claims,
    google_sign_in,
    make_academics,
    make_advisor,
    make_student,
    make_super_admin,
    start_google_sign_in,
)

TIMED_OUT = "Your session timed out. Please sign in again."
SIGNED_OUT = "You have signed out."
DEMO_ADMIN = "demo.owner@example.test"
DEMO_ADVISOR = "demo.helper@example.test"
NOT_LISTED = "someone.else@example.test"


def signed_in(client):
    return "_auth_user_id" in client.session


def at(minutes):
    return mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(minutes=minutes))


class IdleTimeoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_student(academics=make_academics())

    def test_default_is_thirty_minutes_and_every_request_extends_it(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_session_ends_after_thirty_idle_minutes(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("student_home")).status_code, 200)
        with at(31):
            response = self.client.get(reverse("student_home"))
        self.assertRedirects(response, f"{reverse('account_login')}?next={reverse('student_home')}",
                             fetch_redirect_response=False)

    def test_activity_extends_the_session(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_home"))
        for minutes in (20, 40, 60):
            with self.subTest(minutes=minutes), at(minutes):
                self.assertEqual(self.client.get(reverse("student_home")).status_code, 200)


class SessionMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_student(academics=make_academics())

    def expire(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_home"))
        session = self.client.session
        session.flush()

    def test_marker_holds_no_personal_data(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_home"))
        marker = response.cookies[SESSION_MARKER_COOKIE]
        self.assertEqual(marker.value, "1")
        self.assertTrue(marker["httponly"])
        self.assertEqual(marker["samesite"], "Lax")

    def test_timed_out_message(self):
        self.expire()
        response = self.client.get(reverse("student_home"), follow=True)
        self.assertContains(response, TIMED_OUT)
        self.assertNotContains(response, SIGNED_OUT)

    def test_message_is_shown_once(self):
        self.expire()
        self.client.get(reverse("student_home"), follow=True)
        self.assertNotContains(self.client.get(reverse("account_login")), TIMED_OUT)

    def test_returning_to_the_home_address_also_explains(self):
        self.expire()
        response = self.client.get(reverse("home"), follow=True)
        self.assertRedirects(response, reverse("account_login"))
        self.assertContains(response, TIMED_OUT)

    def test_normal_sign_out_says_signed_out(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_home"))
        response = self.client.post(reverse("account_logout"), follow=True)
        self.assertContains(response, SIGNED_OUT)
        self.assertNotContains(response, TIMED_OUT)
        self.assertNotContains(self.client.get(reverse("student_home"), follow=True), TIMED_OUT)

    def test_first_time_visitor_sees_no_message(self):
        self.assertNotContains(self.client.get(reverse("account_login")), TIMED_OUT)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_form_sent_after_timeout_returns_to_its_page(self):
        self.expire()
        page = reverse("student_voice")
        response = self.client.post(reverse("student_complaint_add_information", args=["CMP-2026-00001"]),
                                    {"message": "x"}, HTTP_REFERER=f"http://testserver{page}?page=2")
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["next"], [f"{page}?page=2"])

    def test_form_from_another_site_does_not_set_next(self):
        self.expire()
        response = self.client.post(reverse("student_complaint_add_information", args=["CMP-2026-00001"]),
                                    {"message": "x"}, HTTP_REFERER="https://evil.example.test/page")
        self.assertEqual(response["Location"], reverse("account_login"))


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class ReturnPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.student = make_student(academics=cls.academics)

    def test_returns_to_the_page_after_sign_in(self):
        page = f"{reverse('student_voice')}?page=2"
        response = google_sign_in(self.client, google_claims(STUDENT_EMAIL), next_url=page)
        self.assertRedirects(response, page, fetch_redirect_response=False)

    def test_sign_in_page_carries_next_in_the_post(self):
        response = self.client.get(reverse("account_login"), {"next": reverse("student_voice")})
        self.assertContains(response, f'name="next" value="{reverse("student_voice")}"')

    def test_unsafe_next_goes_home(self):
        for url in ("https://evil.example.test/", "//evil.example.test/", "/\\evil.example.test",
                    "javascript:alert(1)", "http://testserver/student/", "student/voice/"):
            with self.subTest(url=url):
                client = Client()
                response = google_sign_in(client, google_claims(STUDENT_EMAIL), next_url=url)
                self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_is_safe_url_accepts_only_site_paths(self):
        adapter = PortalAccountAdapter()
        self.assertTrue(adapter.is_safe_url("/student/voice/?page=2"))
        for url in ("", "https://evil.example.test/", "//evil.example.test", "/\\evil.example.test"):
            with self.subTest(url=url):
                self.assertFalse(adapter.is_safe_url(url))

    def test_another_roles_page_goes_home(self):
        response = google_sign_in(self.client, google_claims(STUDENT_EMAIL), next_url=reverse("advisor_voice"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_new_student_completes_registration_first(self):
        email = "87654321@student.uol.edu.pk"
        response = google_sign_in(self.client, google_claims(email, sub="sub-new"), next_url=reverse("student_voice"))
        self.assertRedirects(response, reverse("student_voice"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("student_voice")), reverse("student_register"))

    def test_select_account_is_always_requested(self):
        self.assertEqual(settings.SOCIALACCOUNT_PROVIDERS["google"]["AUTH_PARAMS"]["prompt"], "select_account")
        response = self.client.post(reverse("google_login"))
        self.assertEqual(parse_qs(urlparse(response["Location"]).query)["prompt"], ["select_account"])


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class DeniedPageTests(TestCase):
    def assert_denied(self, claims, code, email=None, next_url=None):
        response = google_sign_in(self.client, claims, next_url=next_url)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "accounts/sign_in_denied.html")
        self.assertEqual(response.context["reason_code"], code)
        self.assertContains(response, escape(DENIAL_MESSAGES[code]), status_code=403)
        if email:
            self.assertContains(response, email, status_code=403)
        self.assertContains(response, "Try another account", status_code=403)
        self.assertContains(response, f'action="{reverse("google_login")}', status_code=403)
        self.assertContains(response, "Back to the home page", status_code=403)
        self.assertFalse(signed_in(self.client))
        return response

    def test_personal_gmail(self):
        response = self.assert_denied(google_claims("someone@gmail.example", hd=None), "wrong_email", "someone@gmail.example")
        self.assertContains(response, "Please use your UOL student email, like 12345678@student.uol.edu.pk", status_code=403)

    def test_wrong_student_format(self):
        email = "ali.khan@student.uol.edu.pk"
        self.assert_denied(google_claims(email), "wrong_email", email)

    def test_staff_email_with_no_account(self):
        response = self.assert_denied(google_claims("new.teacher@uol.edu.pk"), "staff_not_set_up", "new.teacher@uol.edu.pk")
        self.assertContains(response, escape("Your staff account hasn't been set up yet. Contact the Super Admin."),
                            status_code=403)
        self.assertFalse(User.objects.exists())

    def test_deactivated_student(self):
        student = make_student()
        User.objects.filter(pk=student.pk).update(is_active=False)
        response = self.assert_denied(google_claims(STUDENT_EMAIL), "deactivated", STUDENT_EMAIL)
        self.assertContains(response, "deactivated", status_code=403)

    def test_deactivated_linked_account(self):
        make_advisor()
        google_sign_in(self.client, google_claims(ADVISOR_EMAIL, sub="sub-a"))
        self.client.logout()
        User.objects.filter(email=ADVISOR_EMAIL).update(is_active=False)
        self.assert_denied(google_claims(ADVISOR_EMAIL, sub="sub-a"), "deactivated", ADVISOR_EMAIL)

    def test_unverified_email(self):
        self.assert_denied(google_claims(STUDENT_EMAIL, email_verified=False), "unverified")

    def test_uol_address_outside_workspace(self):
        self.assert_denied(google_claims(STUDENT_EMAIL, hd=None), "not_uol_google", STUDENT_EMAIL)

    def test_email_is_escaped(self):
        claims = google_claims('"<b>x</b>"@gmail.example', hd=None)
        response = google_sign_in(self.client, claims)
        self.assertNotContains(response, "<b>x</b>", status_code=403)

    def test_try_another_account_keeps_a_safe_next(self):
        page = reverse("student_voice")
        response = self.assert_denied(google_claims("someone@gmail.example", hd=None), "wrong_email", next_url=page)
        self.assertContains(response, f'name="next" value="{page}"', status_code=403)

    def test_try_another_account_shows_the_chooser_again(self):
        google_sign_in(self.client, google_claims("someone@gmail.example", hd=None))
        response = self.client.post(reverse("google_login"))
        self.assertEqual(parse_qs(urlparse(response["Location"]).query)["prompt"], ["select_account"])


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS, DEMO_STAFF_EMAILS=[DEMO_ADMIN, DEMO_ADVISOR])
class DemoStaffTests(TestCase):
    def make_demo_admin(self):
        return make_super_admin(DEMO_ADMIN)

    @override_settings(DEBUG=True)
    def test_listed_email_signs_in_with_debug_on(self):
        user = self.make_demo_admin()
        google_sign_in(self.client, google_claims(DEMO_ADMIN, hd=None))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertRedirects(self.client.get(reverse("home")), reverse("super_admin_home"))

    def test_setting_is_ignored_with_debug_off(self):
        with override_settings(DEBUG=True):
            self.make_demo_admin()
        self.assertEqual(identity.demo_staff_emails(), [])
        self.assertFalse(identity.is_staff_email(DEMO_ADMIN))
        response = google_sign_in(self.client, google_claims(DEMO_ADMIN, hd=None))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.context["reason_code"], "wrong_email")
        self.assertFalse(signed_in(self.client))

    @override_settings(DEBUG=True)
    def test_unlisted_email_is_refused(self):
        response = google_sign_in(self.client, google_claims(NOT_LISTED, hd=None))
        self.assertEqual(response.context["reason_code"], "wrong_email")
        self.assertFalse(signed_in(self.client))

    @override_settings(DEBUG=True)
    def test_listed_email_without_an_account_is_refused(self):
        response = google_sign_in(self.client, google_claims(DEMO_ADMIN, hd=None))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.context["reason_code"], "staff_not_set_up")
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=True)
    def test_listed_email_must_still_be_verified(self):
        self.make_demo_admin()
        response = google_sign_in(self.client, google_claims(DEMO_ADMIN, hd=None, email_verified=False))
        self.assertEqual(response.context["reason_code"], "unverified")
        self.assertFalse(signed_in(self.client))

    @override_settings(DEBUG=True)
    def test_match_is_exact(self):
        self.make_demo_admin()
        for email in (f"x{DEMO_ADMIN}", f"{DEMO_ADMIN}.evil.test", DEMO_ADMIN.replace("example", "exampel")):
            with self.subTest(email=email):
                self.assertFalse(identity.is_demo_staff_email(email))
        self.assertTrue(identity.is_demo_staff_email(DEMO_ADMIN.upper()))

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[STUDENT_EMAIL, "not-an-email"])
    def test_student_and_malformed_entries_are_never_demo_staff(self):
        self.assertEqual(identity.demo_staff_emails(), [])
        response = google_sign_in(self.client, google_claims(STUDENT_EMAIL, hd=None))
        self.assertEqual(response.context["reason_code"], "not_uol_google")


class SeedDemoStaffTests(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        return out.getvalue()

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[])
    def test_without_the_setting_nothing_extra_is_created(self):
        self.run_seed()
        self.assertEqual(User.objects.filter(role=User.Role.SUPER_ADMIN).count(), 1)
        self.assertEqual(User.objects.filter(role=User.Role.BATCH_ADVISOR).count(), 2)

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[DEMO_ADMIN, DEMO_ADVISOR])
    def test_creates_both_roles_and_is_idempotent(self):
        self.run_seed()
        self.assertTrue(User.objects.get(email=DEMO_ADMIN).is_super_admin)
        advisor = User.objects.get(email=DEMO_ADVISOR)
        self.assertTrue(advisor.is_batch_advisor)
        self.assertEqual(set(AdvisorAssignment.objects.filter(advisor=advisor).values_list("section__name", flat=True)),
                         {"DEMO-A", "DEMO-B"})
        for existing in ("demo.admin@uol.edu.pk", "demo.advisor@uol.edu.pk", "12345678@student.uol.edu.pk"):
            self.assertTrue(User.objects.filter(email=existing).exists())
        users, assignments = User.objects.count(), AdvisorAssignment.objects.count()
        self.assertIn("Demo data already present", self.run_seed())
        self.assertEqual((User.objects.count(), AdvisorAssignment.objects.count()), (users, assignments))

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[DEMO_ADMIN])
    def test_one_email_is_only_the_super_admin(self):
        self.run_seed()
        self.assertTrue(User.objects.get(email=DEMO_ADMIN).is_super_admin)
        self.assertFalse(User.objects.filter(email=DEMO_ADVISOR).exists())

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[DEMO_ADMIN, DEMO_ADVISOR])
    def test_existing_account_is_updated_to_its_role(self):
        academics = make_academics()
        user = make_advisor(DEMO_ADMIN, cohorts=[cohort(academics)], full_name="Kept Name")
        self.run_seed()
        user.refresh_from_db()
        self.assertTrue(user.is_super_admin)
        self.assertTrue(user.is_staff and user.is_superuser)
        self.assertEqual(user.full_name, "Kept Name")

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[STUDENT_EMAIL, DEMO_ADVISOR])
    def test_a_student_address_stops_the_seed(self):
        with self.assertRaisesMessage(CommandError, "DEMO_STAFF_EMAILS"):
            self.run_seed()
        self.assertFalse(User.objects.filter(email=DEMO_ADVISOR).exists())
