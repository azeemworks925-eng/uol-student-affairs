"""Academic Terms page (DEC-314, DEC-330)."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from academics import services
from academics.models import AcademicTerm
from accounts.tests.helpers import make_academics, make_advisor, make_student, make_super_admin


class TermPagesBase(TestCase):
    def setUp(self):
        self.admin = make_super_admin()
        self.fall = AcademicTerm.objects.create(name="Fall 2026", start_date=date(2026, 9, 1), end_date=date(2027, 1, 15))
        self.spring = AcademicTerm.objects.create(name="Spring 2026", start_date=date(2026, 2, 1), end_date=date(2026, 6, 15))
        self.client.force_login(self.admin)
        self.url = reverse("super_admin_terms")

    def values(self, **overrides):
        return {"name": "Spring 2027", "start_date": "2027-02-01", "end_date": "2027-06-15", **overrides}

    def current_names(self):
        return list(AcademicTerm.objects.filter(is_current=True).values_list("name", flat=True))


class PermissionTests(TermPagesBase):
    def test_other_roles_get_404(self):
        academics = make_academics()
        posts = [reverse("super_admin_term_add"), reverse("super_admin_term_edit", args=[self.fall.pk]),
                 reverse("super_admin_term_current", args=[self.fall.pk]), reverse("super_admin_term_clear", args=[self.fall.pk])]
        for user in (make_student(academics=academics), make_advisor()):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            for url in posts:
                self.assertEqual(self.client.post(url, self.values()).status_code, 404)
        self.assertEqual(AcademicTerm.objects.count(), 2)
        self.assertEqual(self.current_names(), [])


class TermTests(TermPagesBase):
    def test_add_is_not_current(self):
        self.assertRedirects(self.client.post(reverse("super_admin_term_add"), self.values()), self.url)
        self.assertIsNone(AcademicTerm.objects.get(name="Spring 2027").is_current)

    def test_add_refuses_a_duplicate_name_ignoring_case(self):
        response = self.client.post(reverse("super_admin_term_add"), self.values(name="fall 2026"))
        self.assertContains(response, "already exists", status_code=400)
        self.assertEqual(AcademicTerm.objects.count(), 2)

    def test_edit(self):
        url = reverse("super_admin_term_edit", args=[self.fall.pk])
        self.assertRedirects(self.client.post(url, self.values(name="Fall 2026 Revised")), self.url)
        self.fall.refresh_from_db()
        self.assertEqual((self.fall.name, self.fall.end_date), ("Fall 2026 Revised", date(2027, 6, 15)))

    def test_end_must_be_after_start(self):
        url = reverse("super_admin_term_edit", args=[self.fall.pk])
        for end in ("2027-01-31", "2027-02-01"):
            self.assertContains(self.client.post(url, self.values(end_date=end)), "must be after", status_code=400)
        self.fall.refresh_from_db()
        self.assertEqual(self.fall.name, "Fall 2026")

    def test_a_refused_edit_reopens_its_dialog(self):
        response = self.client.post(reverse("super_admin_term_edit", args=[self.fall.pk]), self.values(end_date="2020-01-01"))
        self.assertContains(response, f'id="dialog-edit-term-{self.fall.pk}" aria-labelledby="edit-term-{self.fall.pk}" data-open-on-load', status_code=400)

    def test_editing_the_current_term_keeps_it_current(self):
        services.set_current_term(self.fall)
        self.client.post(reverse("super_admin_term_edit", args=[self.fall.pk]), self.values(name="Fall Renamed"))
        self.assertEqual(self.current_names(), ["Fall Renamed"])

    def test_make_current_keeps_only_one(self):
        self.client.post(reverse("super_admin_term_current", args=[self.fall.pk]))
        self.assertEqual(self.current_names(), ["Fall 2026"])
        self.client.post(reverse("super_admin_term_current", args=[self.spring.pk]))
        self.assertEqual(self.current_names(), ["Spring 2026"])

    def test_clear_current(self):
        services.set_current_term(self.fall)
        self.client.post(reverse("super_admin_term_clear", args=[self.fall.pk]))
        self.assertEqual(self.current_names(), [])

    def test_clear_on_a_term_that_is_not_current_changes_nothing(self):
        services.set_current_term(self.fall)
        self.client.post(reverse("super_admin_term_clear", args=[self.spring.pk]))
        self.assertEqual(self.current_names(), ["Fall 2026"])

    def test_page_names_the_term_the_overview_uses(self):
        self.assertContains(self.client.get(self.url), "No term is current")
        services.set_current_term(self.fall)
        self.assertContains(self.client.get(self.url), "The Overview analytics use Fall 2026")

    def test_there_is_no_delete_route(self):
        self.assertEqual(self.client.post(f"{self.url}{self.fall.pk}/delete/").status_code, 404)
        self.assertTrue(AcademicTerm.objects.filter(pk=self.fall.pk).exists())
