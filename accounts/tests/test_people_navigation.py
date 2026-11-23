"""Navigation after the move to portal pages (DEC-330)."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .helpers import make_academics, make_advisor, make_student, make_super_admin

DEMO_ADMIN = "owner.demo@gmail.com"
DEMO_ADVISOR = "advisor.demo@gmail.com"


class NavigationTests(TestCase):
    def setUp(self):
        self.a = make_academics()
        self.admin = make_super_admin()
        self.advisor = make_advisor()
        self.student = make_student(academics=self.a)

    def admin_links(self, html):
        return re.findall(r'href="(/admin/[^"]*)"', html)

    def test_the_only_admin_link_for_the_super_admin_is_the_avatar_fallback(self):
        self.client.force_login(self.admin)
        pages = ["super_admin_home", "super_admin_students", "super_admin_student_changes", "super_admin_staff",
                 "super_admin_structure", "super_admin_terms", "super_admin_representatives", "super_admin_categories",
                 "super_admin_complaints", "super_admin_voice", "super_admin_meetings"]
        for name in pages:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertEqual(self.admin_links(html), [reverse("admin:index")])
                menu = html[html.index('class="dropdown-menu dropdown-menu-end sa-account-menu"'):]
                self.assertIn("Advanced: Django admin", menu[:menu.index("</form>")])

    def test_other_roles_have_no_admin_link(self):
        for user, page in ((self.student, "student_home"), (self.advisor, "advisor_home")):
            self.client.force_login(user)
            html = self.client.get(reverse(page)).content.decode()
            self.assertEqual(self.admin_links(html), [])
            self.assertNotIn("Advanced: Django admin", html)

    def test_sidebar_and_new_menu_point_to_the_portal(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("super_admin_home")).content.decode()
        sidebar = html[html.index('<aside class="sa-sidebar"'):html.index("</aside>")]
        for name in ("super_admin_students", "super_admin_staff", "super_admin_structure", "super_admin_terms"):
            self.assertIn(f'href="{reverse(name)}"', sidebar)
        self.assertIn(f'href="{reverse("super_admin_staff")}?new=1"', html)

    def test_detail_pages_keep_their_sidebar_item_current(self):
        self.client.force_login(self.admin)
        for url, label in ((reverse("super_admin_student_detail", args=[self.student.pk]), "Students"),
                           (reverse("super_admin_staff_detail", args=[self.advisor.pk]), "Staff")):
            html = self.client.get(url).content.decode()
            self.assertRegex(html, rf'data-tip="{label}" aria-current="page"')

    def test_setup_state_links_to_the_terms_page(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("super_admin_home")), f'href="{reverse("super_admin_terms")}"')


@override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[DEMO_ADMIN, DEMO_ADVISOR])
class SeedNameTests(TestCase):
    def seed(self):
        call_command("seed_demo", stdout=StringIO())

    def test_names_already_on_the_accounts_are_kept(self):
        User.objects.create_superuser(email=DEMO_ADMIN, full_name="Real Owner Name")
        self.seed()
        self.assertEqual(User.objects.get(email=DEMO_ADMIN).full_name, "Real Owner Name")

    def test_a_blank_name_gets_the_seed_name(self):
        User.objects.create_superuser(email=DEMO_ADMIN, full_name="")
        self.seed()
        self.assertEqual(User.objects.get(email=DEMO_ADMIN).full_name, "Demo Staff Admin")

    def test_new_accounts_get_the_seed_names(self):
        self.seed()
        self.assertEqual(User.objects.get(email=DEMO_ADVISOR).full_name, "Demo Staff Advisor")
