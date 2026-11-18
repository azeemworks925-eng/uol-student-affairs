"""Production frontend: layouts, role navigation, home pages and accessibility hooks."""

import re
from datetime import datetime

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import StudentRegistrationForm
from accounts.presentation import NOTHING_TO_SHOW, Summary, first_name, greeting, personal_summary

from .helpers import cohort, make_academics, make_advisor, make_student, make_super_admin


def section(html, opening):
    """The markup from `opening` to the first closing </nav> after it."""
    start = html.index(opening)
    return html[start:html.index("</nav>", start)]


class PersonalSummaryTests(SimpleTestCase):
    def test_no_updates(self):
        self.assertEqual(personal_summary([]), Summary(NOTHING_TO_SHOW))
        self.assertEqual(NOTHING_TO_SHOW, "Nothing needs your attention today.")

    def test_one_update_is_described_directly(self):
        self.assertEqual(personal_summary(["Your complaint was resolved."]), Summary("Your complaint was resolved."))

    def test_several_updates_lead_with_the_first(self):
        self.assertEqual(
            personal_summary(["First.", "Second."]), Summary("First.", "You have 1 other update.")
        )
        self.assertEqual(
            personal_summary(["First.", "Second.", "Third."]), Summary("First.", "You have 2 other updates.")
        )

    def test_blank_entries_are_ignored(self):
        self.assertEqual(personal_summary(["", None]), Summary(NOTHING_TO_SHOW))


class GreetingTests(SimpleTestCase):
    def test_time_of_day(self):
        tz = timezone.get_current_timezone()
        for hour, expected in [(0, "Good morning"), (11, "Good morning"), (12, "Good afternoon"),
                               (16, "Good afternoon"), (17, "Good evening"), (23, "Good evening")]:
            with self.subTest(hour=hour):
                self.assertEqual(greeting(datetime(2026, 11, 16, hour, 30, tzinfo=tz)), expected)

    def test_first_name(self):
        class Person:
            def __init__(self, full_name):
                self.full_name = full_name

        self.assertEqual(first_name(Person("  Ali Khan ")), "Ali")
        self.assertEqual(first_name(Person("")), "")


class StaticAssetTests(SimpleTestCase):
    def test_self_hosted_assets_are_findable(self):
        for path in [
            "css/app.css",
            "fonts/Inter-latin-variable.woff2",
            "fonts/Newsreader-latin-variable.woff2",
            "vendor/bootstrap-5.3.3/bootstrap.min.css",
            "vendor/bootstrap-5.3.3/bootstrap.bundle.min.js",
        ]:
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))


class StudentHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")

    def setUp(self):
        self.client.force_login(self.student)
        self.response = self.client.get(reverse("student_home"))
        self.html = self.response.content.decode()

    def test_uses_student_template_and_app_layout(self):
        self.assertTemplateUsed(self.response, "accounts/student_home.html")
        self.assertTemplateUsed(self.response, "layouts/app.html")

    def test_exact_cohort_and_greeting(self):
        self.assertContains(self.response, "Fall 2024 · Semester 4 · Section A")
        self.assertContains(self.response, ", Ali.")

    def test_zero_state_summary(self):
        self.assertContains(self.response, NOTHING_TO_SHOW)
        self.assertContains(self.response, "No updates yet.")
        self.assertContains(self.response, "No open issues in your section.")

    def test_quick_access_lists_three_actions_without_dead_links(self):
        quick = section(self.html, '<nav class="sa-quick"')
        for label in ("Submit a complaint", "Student Voice", "My meetings"):
            self.assertIn(label, quick)
        # Only built destinations are links: complaints (Part 2). The others stay unavailable.
        self.assertEqual(re.findall(r'<a [^>]*href="([^"]+)"', quick), [reverse("student_complaint_new")])
        self.assertEqual(quick.count('aria-disabled="true"'), 2)

    def test_bottom_navigation_has_exactly_four_destinations(self):
        bottom = section(self.html, '<nav class="sa-bottomnav"')
        items = re.findall(r"<(?:a|span) (?:href|role)=", bottom)
        self.assertEqual(len(items), 4)
        for label in ("Home", "Complaints", "Voice", "Meetings"):
            self.assertIn(label, bottom)
        self.assertNotIn("More", bottom)

    def test_active_navigation_is_marked_current(self):
        self.assertRegex(self.html, r'<a class="sa-nav-link" href="/[^"]*" aria-current="page">.*Home</a>')
        self.assertEqual(self.html.count('aria-current="page"'), 2)  # sidebar and bottom navigation

    def test_unbuilt_destinations_are_not_links(self):
        self.assertIn("Soon", self.html)
        for label in ("Student Voice", "Meetings"):
            self.assertNotRegex(self.html, r'<a class="sa-nav-link"[^>]*>.*{}</a>'.format(label))
        self.assertRegex(self.html, r'<a class="sa-nav-link" href="{}">.*Complaints</a>'.format(re.escape(reverse("student_complaints"))))

    def test_no_staff_drawer_or_other_students(self):
        self.assertNotIn('id="sa-drawer"', self.html)
        other = make_student("87654321@student.uol.edu.pk", academics=self.academics, full_name="Zara Other")
        self.assertNotContains(self.client.get(reverse("student_home")), other.full_name)

    def test_sign_out_is_a_post_form(self):
        self.assertRegex(self.html, r'<form method="post" action="{}"'.format(re.escape(reverse("account_logout"))))


class AdvisorHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics), cohort(cls.academics, section="other_section")])
        cls.unassigned = make_advisor("advisor2@uol.edu.pk")

    def test_rail_and_assigned_cohorts(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_home"))
        html = response.content.decode()

        self.assertTemplateUsed(response, "accounts/advisor_home.html")
        self.assertIn('<nav class="sa-rail"', html)
        self.assertNotIn('<aside class="sa-sidebar"', html)
        self.assertNotIn('class="sa-bottomnav"', html)
        self.assertIn('id="sa-drawer"', html)
        self.assertContains(response, "You advise 2 cohorts.")
        self.assertContains(response, "Semester 4 · Section A")
        self.assertContains(response, "Semester 4 · Section B")
        self.assertRegex(html, r'class="sa-rail-link" href="{}"[^>]*aria-current="page"'.format(reverse("advisor_home")))

    def test_no_assignments(self):
        self.client.force_login(self.unassigned)
        self.assertContains(self.client.get(reverse("advisor_home")), "No cohorts are assigned to you yet.")


class SuperAdminHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_super_admin()

    def setUp(self):
        self.client.force_login(self.admin)
        self.response = self.client.get(reverse("super_admin_home"))
        self.html = self.response.content.decode()

    def test_grouped_sidebar_without_statistics(self):
        self.assertTemplateUsed(self.response, "accounts/super_admin_home.html")
        sidebar = self.html[self.html.index('<aside class="sa-sidebar"'):self.html.index("</aside>")]
        for heading in ("Oversight", "People", "Configuration"):
            self.assertIn(heading, sidebar)
        self.assertNotIn("Statistics", self.html)  # DEC-306

    def test_manage_links_reach_existing_admin_pages(self):
        for name in ("admin:accounts_studentprofile_changelist", "admin:accounts_user_changelist"):
            self.assertIn(reverse(name), self.html)
        self.assertIn(reverse("admin:app_list", kwargs={"app_label": "academics"}), self.html)
        self.assertIn("?role__exact=batch_advisor", self.html)
        # Each linked admin page actually opens for the Super Admin.
        for url in re.findall(r'class="btn btn-sa-secondary btn-sm" href="([^"]+)"', self.html):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url.replace("&amp;", "&")).status_code, 200)

    def test_empty_overview_has_no_invented_figures(self):
        # No current academic term: the Stage 4b setup state, never all-time figures (DEC-316).
        self.assertContains(self.response, "Set the current academic term to see this term’s figures.")
        self.assertNotContains(self.response, 'class="sa-analytics"')


class AuthLayoutTests(TestCase):
    def test_login_uses_auth_layout(self):
        response = self.client.get(reverse("account_login"))
        self.assertTemplateUsed(response, "layouts/auth.html")
        self.assertContains(response, "not configured")

    def test_registration_page_shows_sap_id_and_marks_errors(self):
        academics = make_academics()
        self.client.force_login(make_student(full_name=""))
        response = self.client.get(reverse("student_register"))
        self.assertTemplateUsed(response, "layouts/auth.html")
        self.assertContains(response, "12345678")

        response = self.client.post(reverse("student_register"), {"full_name": "", "batch": academics["batch"].pk})
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_full_name-error"')
        self.assertContains(response, 'id="id_full_name-error"')
        self.assertContains(response, 'id="id_semester-error"')

    def test_valid_form_has_no_error_attributes(self):
        form = StudentRegistrationForm()
        self.assertNotIn("aria-invalid", str(form["full_name"]))


class RoleNavigationScopeTests(TestCase):
    """Each role's shell lists only its own destinations. Views still enforce access (test_permissions)."""

    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.student = make_student(academics=cls.academics)
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)])
        cls.admin = make_super_admin()

    def page(self, user, url_name):
        self.client.force_login(user)
        return self.client.get(reverse(url_name)).content.decode()

    def test_student_shell_has_no_staff_destinations(self):
        html = self.page(self.student, "student_home")
        self.assertNotIn("/admin/", html)
        for label in ("Collective Issues", "Representatives", "Statistics", "Batch Advisors", "CR/GR Management"):
            self.assertNotIn(label, html)

    def test_advisor_shell_has_no_super_admin_destinations(self):
        html = self.page(self.advisor, "advisor_home")
        self.assertNotIn("/admin/", html)
        for label in ("Oversight", "Configuration", "Batch Advisors", "CR/GR Management", "Complaint Categories"):
            self.assertNotIn(label, html)

    def test_hidden_navigation_is_not_the_only_barrier(self):
        self.client.force_login(self.student)
        for name in ("advisor_home", "super_admin_home"):
            self.assertNotEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertNotEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.client.force_login(self.advisor)
        self.assertNotEqual(self.client.get(reverse("super_admin_home")).status_code, 200)
        self.assertNotEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_anonymous_visitors_get_no_shell(self):
        for name in ("student_home", "advisor_home", "super_admin_home", "student_register"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_navigation_is_a_landmark_and_icons_are_decorative(self):
        for user, name in ((self.student, "student_home"), (self.advisor, "advisor_home"), (self.admin, "super_admin_home")):
            with self.subTest(page=name):
                html = self.page(user, name)
                if user == self.advisor:
                    self.assertIn('<nav class="sa-rail" aria-label="Main navigation">', html)
                else:
                    self.assertIn('<nav aria-label="Main navigation">', html)
                svgs = re.findall(r"<svg class=\"sa-i\"[^>]*>", html)
                self.assertTrue(svgs)
                self.assertTrue(all('aria-hidden="true"' in tag for tag in svgs), svgs)


class SignInFlowPageTests(TestCase):
    """django-allauth pages a user can reach use the portal layout, not allauth's default."""

    def assert_portal_page(self, response, text):
        self.assertTemplateUsed(response, "layouts/auth.html")
        self.assertContains(response, text, status_code=response.status_code)
        self.assertNotContains(response, "Menu:", status_code=response.status_code)

    def test_login_cancelled(self):
        self.assert_portal_page(self.client.get(reverse("socialaccount_login_cancelled")), "Sign-in cancelled.")

    def test_login_error(self):
        response = self.client.get(reverse("socialaccount_login_error"))
        self.assertEqual(response.status_code, 401)
        self.assert_portal_page(response, "Sign-in did not complete.")

    def test_account_inactive(self):
        self.assert_portal_page(self.client.get(reverse("account_inactive")), "This account is inactive.")

    def test_sign_out_confirmation_posts_and_shows_message(self):
        self.client.force_login(make_super_admin())
        response = self.client.get(reverse("account_logout"))
        self.assert_portal_page(response, "Sign out of Student Affairs?")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

        response = self.client.post(reverse("account_logout"), follow=True)
        self.assertRedirects(response, reverse("account_login"))
        self.assertContains(response, 'class="sa-message"')
        self.assertContains(response, "You have signed out.")

    def test_other_allauth_pages_fall_back_to_the_portal_layout(self):
        from django.template import engines
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        page = engines["django"].from_string(
            '{% extends "account/base_entrance.html" %}{% block head_title %}Example{% endblock %}'
            "{% block content %}<p>Example body</p>{% endblock %}"
        ).render({}, request)
        self.assertIn("<title>Example · UOL Student Affairs</title>", page)
        self.assertIn('class="sa-auth-card"', page)
        self.assertIn("<p>Example body</p>", page)
        self.assertNotIn("Menu:", page)
