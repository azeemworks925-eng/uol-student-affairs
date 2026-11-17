"""Academic term administration in the Django admin (Complaints Part 4 Stage 4a)."""

from datetime import date
from unittest import mock

from django.contrib import admin
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from academics import services
from academics.admin import AcademicTermAdmin
from academics.models import AcademicTerm, ProtectedTermError
from accounts.tests.helpers import make_academics, make_advisor, make_student, make_super_admin

CHANGELIST = reverse("admin:academics_academicterm_changelist")
ADD = reverse("admin:academics_academicterm_add")


def change_url(term):
    return reverse("admin:academics_academicterm_change", args=[term.pk])


def form_data(name="Fall 2026", start="2026-09-01", end="2027-01-15", **extra):
    return {"name": name, "start_date": start, "end_date": end, **extra}


def current_pks():
    return list(AcademicTerm.objects.filter(is_current=True).values_list("pk", flat=True))


class TermAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.head = make_super_admin()
        cls.fall = AcademicTerm.objects.create(name="Fall 2026", start_date=date(2026, 9, 1), end_date=date(2027, 1, 15))
        cls.spring = AcademicTerm.objects.create(name="Spring 2026", start_date=date(2026, 2, 1), end_date=date(2026, 6, 30))

    def setUp(self):
        self.client.force_login(self.head)

    def act(self, action, *terms, follow=True):
        return self.client.post(
            CHANGELIST, {"action": action, "_selected_action": [t.pk for t in terms]}, follow=follow
        )

    def messages(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]


class AccessTests(TermAdminTestCase):
    def test_registered_in_academic_structure(self):
        self.assertIsInstance(admin.site._registry[AcademicTerm], AcademicTermAdmin)
        response = self.client.get(reverse("admin:app_list", kwargs={"app_label": "academics"}))
        self.assertContains(response, CHANGELIST)

    def test_super_admin_can_list_add_and_change(self):
        for url in (CHANGELIST, ADD, change_url(self.fall)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_other_roles_and_anonymous_are_refused(self):
        academics = make_academics()
        student = make_student(academics=academics)
        advisor = make_advisor()
        inactive_head = make_super_admin("former@uol.edu.pk")
        inactive_head.is_active = False
        inactive_head.save()
        for user in (None, student, advisor, inactive_head):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in (CHANGELIST, ADD, change_url(self.fall)):
                with self.subTest(user=getattr(user, "email", "anonymous"), url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertNotIn(CHANGELIST, response["Location"].split("?")[0])
            with self.subTest(user=getattr(user, "email", "anonymous"), action="make_current"):
                self.act("make_current", self.fall, follow=False)
                self.assertEqual(current_pks(), [])

    def test_terms_cannot_be_deleted(self):
        response = self.client.get(reverse("admin:academics_academicterm_delete", args=[self.fall.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("admin:academics_academicterm_delete", args=[self.fall.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        choices = [name for name, _ in self.client.get(CHANGELIST).context["action_form"].fields["action"].choices]
        self.assertEqual(choices, ["", "make_current", "clear_current"])
        self.act("delete_selected", self.fall, self.spring)
        self.assertEqual(AcademicTerm.objects.count(), 2)


class FormTests(TermAdminTestCase):
    def test_current_flag_is_not_a_form_field(self):
        response = self.client.get(change_url(self.fall))
        self.assertNotIn("is_current", response.context["adminform"].form.fields)
        self.assertNotContains(response, 'name="is_current"')
        self.assertContains(response, "Not current")

    def test_posting_the_current_flag_is_ignored(self):
        response = self.client.post(change_url(self.fall), form_data(is_current="on"))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(ADD, form_data(name="Summer 2026", start="2026-07-01", end="2026-08-15", is_current="on"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(current_pks(), [])

    def test_adding_a_term(self):
        response = self.client.post(ADD, form_data(name="  Summer   2026 ", start="2026-07-01", end="2026-08-15"))
        self.assertEqual(response.status_code, 302)
        term = AcademicTerm.objects.get(name="Summer 2026")
        self.assertEqual((term.start_date, term.end_date, term.is_current), (date(2026, 7, 1), date(2026, 8, 15), None))

    def test_reversed_dates_are_a_form_error(self):
        response = self.client.post(ADD, form_data(name="Backwards", start="2026-09-02", end="2026-09-01"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["adminform"].form.errors["end_date"], ["The end date cannot be before the start date."])
        self.assertFalse(AcademicTerm.objects.filter(name="Backwards").exists())

    def test_editing_the_current_term_keeps_it_current(self):
        services.set_current_term(self.fall)
        response = self.client.post(change_url(self.fall), form_data(name="Fall 2026 (main)", end="2027-01-20"))
        self.assertEqual(response.status_code, 302)
        self.fall.refresh_from_db()
        self.assertEqual((self.fall.name, self.fall.end_date, self.fall.is_current), ("Fall 2026 (main)", date(2027, 1, 20), True))

    def test_duplicate_names_are_a_form_error(self):
        for name in ("Fall 2026", "fall 2026", "FÁLL 2026"):
            with self.subTest(name=name):
                response = self.client.post(ADD, form_data(name=name))
                self.assertEqual(response.status_code, 200)
                self.assertIn("name", response.context["adminform"].form.errors)
        self.assertEqual(AcademicTerm.objects.count(), 2)

    def test_a_database_conflict_while_saving_is_reported_not_a_server_error(self):
        with mock.patch.object(AcademicTerm, "save", side_effect=IntegrityError("duplicate")):
            response = self.client.post(ADD, form_data(name="Race 2026"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", [level for level, _ in self.messages(response)])
        self.assertFalse(AcademicTerm.objects.filter(name="Race 2026").exists())


class StaleFormTests(TermAdminTestCase):
    """Regressions for the review of PR #18: the change form loads the term, and another Super
    Admin changes the current term before this form is saved. The switch is simulated at the
    last moment before the save (in save_model), on the same request; the real two-connection
    races are in academics.tests.test_terms.ConcurrencyTests."""

    def submit_after(self, change, term, **data):
        real_save_model = AcademicTermAdmin.save_model

        def concurrent_change_then_save(admin_self, request, obj, form, changed):
            change()
            return real_save_model(admin_self, request, obj, form, changed)

        with mock.patch.object(AcademicTermAdmin, "save_model", concurrent_change_then_save):
            return self.client.post(change_url(term), form_data(**data), follow=True)

    def test_editing_the_old_current_term_after_a_switch_is_saved_safely(self):
        # Before the fix: HTTP 500 (ProtectedTermError).
        services.set_current_term(self.fall)
        response = self.submit_after(
            lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.spring.pk)),
            self.fall, name="Fall 2026 (renamed)",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][1], 302)
        self.assertEqual(self.messages(response)[0][0], "success")
        fall = AcademicTerm.objects.get(pk=self.fall.pk)
        self.assertEqual((fall.name, fall.is_current), ("Fall 2026 (renamed)", None))
        self.assertEqual(current_pks(), [self.spring.pk])
        self.assertEqual(AcademicTerm.objects.get(pk=self.spring.pk).name, "Spring 2026")

    def test_editing_a_term_made_current_meanwhile_keeps_it_current(self):
        # Before the fix (in the narrower window): a silent lost update, leaving no current term.
        response = self.submit_after(
            lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.fall.pk)),
            self.fall, name="Fall 2026 (renamed)",
        )
        self.assertEqual(response.redirect_chain[-1][1], 302)
        fall = AcademicTerm.objects.get(pk=self.fall.pk)
        self.assertEqual((fall.name, fall.is_current), ("Fall 2026 (renamed)", True))
        self.assertEqual(current_pks(), [self.fall.pk])

    def test_a_refused_flag_change_is_a_message_not_a_server_error(self):
        # A safeguard: the form cannot send the flag, but if a save is refused it is reported.
        with mock.patch.object(AcademicTerm, "save", side_effect=ProtectedTermError("refused")):
            response = self.client.post(change_url(self.fall), form_data(name="Never saved"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.messages(response),
            [("error", "The term was not saved because it conflicts with a change made at the same time "
                       "(for example, a term with the same name). Nothing was changed. Check the term "
                       "list, then try again.")],
        )
        self.assertEqual(AcademicTerm.objects.get(pk=self.fall.pk).name, "Fall 2026")

    def test_unrelated_errors_are_not_swallowed(self):
        with mock.patch.object(AcademicTerm, "save", side_effect=ValueError("unrelated")):
            with self.assertRaises(ValueError):
                self.client.post(change_url(self.fall), form_data(name="Never saved"))
        self.assertEqual(AcademicTerm.objects.get(pk=self.fall.pk).name, "Fall 2026")


class ListTests(TermAdminTestCase):
    def test_list_shows_the_current_designation(self):
        services.set_current_term(self.fall)
        response = self.client.get(CHANGELIST)
        self.assertContains(response, "Current term", count=2)  # column heading and the current row
        self.assertContains(response, "Not current", count=1)


class ActionTests(TermAdminTestCase):
    def test_make_current_requires_exactly_one_term(self):
        response = self.act("make_current", self.fall, self.spring)
        self.assertEqual(self.messages(response), [("error", "Select exactly one term to make it the current term.")])
        self.assertEqual(current_pks(), [])

    def test_make_current(self):
        response = self.act("make_current", self.fall)
        self.assertEqual(self.messages(response), [("success", "Fall 2026 is now the current term.")])
        response = self.act("make_current", self.spring)
        self.assertEqual(
            self.messages(response), [("success", "Spring 2026 is now the current term (it replaces Fall 2026).")]
        )
        response = self.act("make_current", self.spring)
        self.assertEqual(self.messages(response), [("info", "Spring 2026 is already the current term.")])
        self.assertEqual(current_pks(), [self.spring.pk])

    def test_clear_requires_the_current_term_alone(self):
        services.set_current_term(self.fall)
        for selection in ((self.spring,), (self.fall, self.spring)):
            with self.subTest(selection=selection):
                response = self.act("clear_current", *selection)
                self.assertEqual(
                    self.messages(response),
                    [("error", "To clear the current term, select the current term and nothing else.")],
                )
        self.assertEqual(current_pks(), [self.fall.pk])

    def test_clear_current(self):
        services.set_current_term(self.fall)
        response = self.act("clear_current", self.fall)
        self.assertEqual(self.messages(response), [("success", "Fall 2026 is no longer the current term. No term is current now.")])
        self.assertEqual(current_pks(), [])

    def test_clear_when_none_is_current(self):
        response = self.act("clear_current", self.fall)
        self.assertEqual(self.messages(response)[0][0], "error")

    def test_a_concurrent_switch_is_reported_safely(self):
        services.set_current_term(self.fall)
        real_clear = services.clear_current_term

        def switch_first(expected):
            # Another Super Admin switches the term after this request read the selection.
            services.set_current_term(self.spring)
            return real_clear(expected=expected)

        with mock.patch.object(services, "clear_current_term", side_effect=switch_first):
            response = self.act("clear_current", self.fall)
        self.assertEqual(
            self.messages(response),
            [("error", "No change was made: the current term changed at the same time. Spring 2026 is now the current term.")],
        )
        self.assertEqual(current_pks(), [self.spring.pk])

    def test_a_database_conflict_is_reported_safely(self):
        with mock.patch.object(services, "_change_current", side_effect=IntegrityError("duplicate")):
            response = self.act("make_current", self.fall)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.messages(response),
            [("error", "No change was made. The current term changed at the same time. Please try again.")],
        )
        self.assertEqual(current_pks(), [])
