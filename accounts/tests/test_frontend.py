"""Production frontend: layouts, role navigation, home pages and accessibility hooks."""

import re
from datetime import datetime
from unittest import mock

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import StudentRegistrationForm
from accounts.presentation import NOTHING_TO_SHOW, Summary, first_name, greeting, personal_summary

from accounts import navigation, views
from accounts.models import User

from .helpers import GOOGLE_PROVIDERS, cohort, make_academics, make_advisor, make_student, make_super_admin

FOOTER = "An independent student project, not an official University of Lahore system."
UNBUILT_WORDING = ("Soon", "not available yet", "Available soon", 'aria-disabled="true"')


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
            "css/admin-forest.css",
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

    def test_quick_access_shows_only_built_actions(self):
        quick = section(self.html, '<nav class="sa-quick"')
        # Only built destinations appear: complaints, Student Voice and meetings.
        self.assertEqual(re.findall(r'<a [^>]*href="([^"]+)"', quick), [reverse("student_complaint_new"), reverse("student_voice"), reverse("student_meetings")])
        self.assertIn("Submit a complaint", quick)
        self.assertIn("Raise a problem with your Batch Advisor", quick)
        self.assertIn("Student Voice", quick)
        for label in UNBUILT_WORDING:
            self.assertNotIn(label, quick)

    def test_quick_access_keeps_unbuilt_actions_for_later(self):
        labels = [item["label"] for item in views.QUICK_ACCESS]
        self.assertEqual(labels, ["Submit a complaint", "Student Voice", "My meetings"])
        built = [dict(item) for item in views.QUICK_ACCESS]
        built[2]["url_name"] = "student_complaints"  # stands in for the meetings page once it exists
        with mock.patch.object(views, "QUICK_ACCESS", built):
            self.assertEqual([item["label"] for item in views.quick_access()], labels)

    def test_bottom_navigation_lists_only_built_destinations(self):
        bottom = section(self.html, '<nav class="sa-bottomnav"')
        self.assertEqual(re.findall(r'<a href="([^"]+)"', bottom),
                         [reverse("student_home"), reverse("student_complaints"), reverse("student_voice"), reverse("student_meetings")])
        self.assertIn("Voice", bottom)
        for label in ("More", *UNBUILT_WORDING):
            self.assertNotIn(label, bottom)

    def test_active_navigation_is_marked_current(self):
        self.assertRegex(self.html, r'<a class="sa-nav-link" href="/[^"]*"[^>]*aria-current="page">.*Home</span></a>')
        self.assertEqual(self.html.count('aria-current="page"'), 3)  # sidebar, phone drawer, bottom navigation

    def test_unbuilt_destinations_are_not_rendered(self):
        for text in UNBUILT_WORDING:
            self.assertNotIn(text, self.html)
        self.assertRegex(self.html, r'<a class="sa-nav-link" href="{}"[^>]*>.*Complaints</span></a>'.format(re.escape(reverse("student_complaints"))))

    def test_phone_drawer_and_no_other_students(self):
        self.assertIn('id="sa-drawer"', self.html)
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

    def test_sidebar_and_assigned_cohorts(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_home"))
        html = response.content.decode()

        self.assertTemplateUsed(response, "accounts/advisor_home.html")
        self.assertIn('<aside class="sa-sidebar"', html)
        self.assertNotIn('sa-rail-link', html)  # the old fixed advisor rail is gone
        self.assertNotIn('class="sa-bottomnav"', html)
        self.assertIn('id="sa-drawer"', html)
        self.assertContains(response, "You advise 2 cohorts.")
        self.assertContains(response, "Semester 4 · Section A")
        self.assertContains(response, "Semester 4 · Section B")
        self.assertRegex(html, r'class="sa-nav-link" href="{}"[^>]*aria-current="page"'.format(reverse("advisor_home")))

    def test_sidebar_shows_only_built_destinations(self):
        self.client.force_login(self.advisor)
        html = self.client.get(reverse("advisor_home")).content.decode()
        sidebar = html[html.index('<aside class="sa-sidebar"'):html.index("</aside>")]
        self.assertEqual(re.findall(r'class="sa-nav-link" href="[^"]+" data-tip="([^"]+)"', sidebar), ["Overview", "Complaints", "Student Voice", "Meetings", "Representatives"])
        for text in ("Collective Issues", "Statistics", *UNBUILT_WORDING):
            self.assertNotIn(text, html)

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

    def test_sidebar_hides_unbuilt_destinations(self):
        sidebar = self.html[self.html.index('<aside class="sa-sidebar"'):self.html.index("</aside>")]
        labels = re.findall(r'<a class="sa-nav-link" href="[^"]+"[^>]*>.*?</svg><span class="sa-nav-text">([^<]+)</span></a>', sidebar)
        self.assertEqual(labels, ["Overview", "Complaints", "Student Voice", "Meetings", "Students", "Batch Advisors", "CR/GR Management",
                                  "Academic Structure", "Complaint Categories"])
        for text in ("Collective Issues", "Calendar", *UNBUILT_WORDING):
            self.assertNotIn(text, self.html)

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
    @override_settings(SOCIALACCOUNT_PROVIDERS={"google": {"SCOPE": ["openid", "email", "profile"]}})  # no client set up
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


class LandingPageTests(TestCase):
    """The public landing page at "/" (signed-out visitors only)."""

    def test_signed_out_visitors_see_the_landing_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/landing.html")
        self.assertTemplateUsed(response, "layouts/public.html")
        for text in ("Raise a concern. Follow it through to resolved.", "How it works", "Submit", "Track",
                     "Resolved", "Complaints", "Student Voice", "Meetings", FOOTER):
            self.assertContains(response, text)
        html = response.content.decode()
        self.assertEqual(html.count('class="sa-display"'), 1)  # one display-size moment
        self.assertIn('class="sa-journey sa-journey--steps"', html)  # the status journey look
        self.assertNotIn('<aside class="sa-sidebar"', html)

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
    def test_sign_in_is_one_csrf_protected_post(self):
        client = self.client_class(enforce_csrf_checks=True)
        html = client.get(reverse("home")).content.decode()
        forms = re.findall(r'<form method="post" action="([^"]+)" class="sa-signin-form">(.*?)</form>', html, re.S)
        self.assertEqual(len(forms), 1)
        action, body = forms[0]
        self.assertEqual(action, reverse("google_login"))
        self.assertIn('name="csrfmiddlewaretoken"', body)
        self.assertIn("Sign in with Google", body)
        self.assertEqual(html.count("btn-sa-primary"), 1)
        self.assertNotRegex(html, r'<a [^>]*href="{}'.format(re.escape(reverse("google_login"))))

    def test_signed_in_users_still_go_to_their_role_home(self):
        academics = make_academics()
        for user, page in ((make_student(academics=academics), "student_home"),
                           (make_advisor(), "advisor_home"), (make_super_admin(), "super_admin_home")):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertRedirects(self.client.get(reverse("home")), reverse(page), fetch_redirect_response=False)


class PublicAuthPageTests(TestCase):
    """Sign-in and refusal pages share the landing page's header and footer and link back to it."""

    def assert_public_page(self, response):
        self.assertTemplateUsed(response, "layouts/public.html")
        self.assertContains(response, FOOTER, status_code=response.status_code)
        self.assertContains(response, f'<a class="sa-wordmark" href="{reverse("home")}">', status_code=response.status_code)

    def test_sign_in_page_links_back_to_the_landing_page(self):
        response = self.client.get(reverse("account_login"))
        self.assert_public_page(response)
        self.assertContains(response, "Back to the home page")

    def test_refusal_pages_offer_a_way_back(self):
        for url_name, status in (("account_inactive", 200), ("socialaccount_login_cancelled", 200),
                                 ("socialaccount_login_error", 401)):
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, status)
                self.assert_public_page(response)
                self.assertContains(response, "Back to the home page", status_code=status)
                self.assertContains(response, f'href="{reverse("account_login")}"', status_code=status)

    def test_sign_in_denied_page(self):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = make_student()
        page = render_to_string("accounts/sign_in_denied.html", {"reason": "Use your UOL Google account."}, request)
        self.assertIn("We couldn't sign you in.", page)
        self.assertIn("Use your UOL Google account.", page)
        self.assertIn("Back to the home page", page)
        self.assertIn(FOOTER, page)


class NavigationDataTests(TestCase):
    """Unbuilt destinations stay in the navigation data and appear as soon as their url_name is set."""

    def test_unbuilt_items_stay_in_the_data(self):
        unbuilt = {role: [item.label for _, items in groups for item in items if not item.url_name]
                   for role, groups in navigation.NAVIGATION.items()}
        self.assertEqual(unbuilt[User.Role.STUDENT], [])
        self.assertEqual(unbuilt[User.Role.BATCH_ADVISOR], ["Collective Issues", "Statistics"])
        self.assertEqual(unbuilt[User.Role.SUPER_ADMIN], ["Collective Issues"])

    def test_an_item_reappears_when_its_url_name_is_set(self):
        heading, items = navigation.NAVIGATION[User.Role.STUDENT][0]
        # "student_complaints" stands in for the Meetings page once it exists.
        built = [navigation.NavItem(i.label, i.icon, "student_complaints") if i.label == "Meetings" else i for i in items]
        self.client.force_login(make_student(academics=make_academics()))
        with mock.patch.dict(navigation.NAVIGATION, {User.Role.STUDENT: [(heading, built)]}):
            html = self.client.get(reverse("student_home")).content.decode()
        self.assertIn("Meetings", html)

    def test_groups_with_nothing_built_are_left_out(self):
        groups = [("Later", [navigation.NavItem("Collective Issues", "hand")]), *navigation.NAVIGATION[User.Role.SUPER_ADMIN]]
        self.client.force_login(make_super_admin())
        with mock.patch.dict(navigation.NAVIGATION, {User.Role.SUPER_ADMIN: groups}):
            html = self.client.get(reverse("super_admin_home")).content.decode()
        self.assertNotIn("Later", html)
        self.assertIn("Oversight", html)


class AdminForestStyleTests(TestCase):
    """The Django admin wears the portal's wordmark and Forest styles; its behaviour is unchanged."""

    def setUp(self):
        self.client.force_login(make_super_admin())

    def test_admin_pages_have_wordmark_back_link_and_forest_css(self):
        for url in (reverse("admin:index"), reverse("admin:accounts_studentprofile_changelist"),
                    reverse("admin:app_list", kwargs={"app_label": "academics"}),
                    reverse("admin:academics_academicterm_changelist")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "admin/base_site.html")
                self.assertContains(response, 'class="sa-admin-wordmark"')
                self.assertContains(response, f'<a class="sa-admin-back" href="{reverse("home")}">Back to portal</a>')
                self.assertContains(response, "css/admin-forest.css")
                self.assertContains(response, f'action="{reverse("admin:logout")}"')
                self.assertNotContains(response, "Django administration")
