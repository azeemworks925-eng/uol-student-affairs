"""Students pages for the Super Admin (DEC-330)."""

from django.test import TestCase
from django.urls import reverse

from academics.models import Section
from accounts.models import CohortRepresentation, StudentProfileChange, User
from accounts.representation import Cohort, appoint_representatives

from .helpers import make_academics, make_advisor, make_student, make_super_admin


def sap(number):
    return f"{number:08d}@student.uol.edu.pk"


class StudentPagesBase(TestCase):
    def setUp(self):
        self.a = make_academics()
        self.admin = make_super_admin()
        self.student = make_student(sap(10000001), academics=self.a, full_name="Ayesha Khan")
        self.other = make_student(sap(20000002), academics=self.a, full_name="Bilal Ahmed",
                                  cohort=(self.a["other_batch"], self.a["other_semester"], self.a["other_section"]))
        self.client.force_login(self.admin)
        self.list_url = reverse("super_admin_students")

    def detail(self, user=None):
        return reverse("super_admin_student_detail", args=[(user or self.student).pk])

    def edit(self, user=None, **overrides):
        user = user or self.student
        data = {"full_name": user.full_name, "batch": user.student_profile.batch_id,
                "semester": user.student_profile.semester_id, "section": user.student_profile.section_id, **overrides}
        return self.client.post(reverse("super_admin_student_edit", args=[user.pk]), data)

    def set_active(self, user, active, **extra):
        return self.client.post(reverse("super_admin_student_active", args=[user.pk]),
                                {"active": "1" if active else "0", **extra})

    def represented_cohort(self):
        """A cohort of four with a CR and GR, so a departing CR needs a replacement."""
        cr = self.student
        gr = make_student(sap(10000003), academics=self.a, full_name="Sara Noor")
        spare = make_student(sap(10000004), academics=self.a, full_name="Hina Ali")
        make_student(sap(10000005), academics=self.a, full_name="Omar Raza")
        cohort = Cohort(self.a["batch"].pk, self.a["semester"].pk, self.a["section"].pk)
        appoint_representatives(self.admin, cohort, cr=cr, gr=gr)
        return cr, gr, spare


class PermissionTests(StudentPagesBase):
    def test_other_roles_get_404_on_every_page_and_action(self):
        urls = [self.list_url, reverse("super_admin_student_changes"), self.detail()]
        posts = [self.list_url, reverse("super_admin_student_edit", args=[self.student.pk]),
                 reverse("super_admin_student_active", args=[self.student.pk])]
        for user in (self.other, make_advisor()):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404, url)
            for url in posts:
                self.assertEqual(self.client.post(url, {"active": "0", "full_name": "X"}).status_code, 404, url)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
        self.assertEqual(self.student.full_name, "Ayesha Khan")

    def test_signed_out_visitor_is_sent_to_sign_in(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.list_url).status_code, 302)

    def test_a_staff_id_is_not_a_student_page(self):
        self.assertEqual(self.client.get(self.detail(self.admin)).status_code, 404)


class ListTests(StudentPagesBase):
    def names(self, **query):
        response = self.client.get(self.list_url, query)
        self.assertEqual(response.status_code, 200)
        return [row.name for row in response.context["page"]]

    def test_search_uses_name_words_full_name_and_sap_prefixes(self):
        self.assertEqual(self.names(q="kha"), ["Ayesha Khan"])
        self.assertEqual(self.names(q="ayesha k"), ["Ayesha Khan"])
        self.assertEqual(self.names(q="2000"), ["Bilal Ahmed"])
        self.assertEqual(self.names(q="zzz"), [])

    def test_search_is_a_prefix_match(self):
        self.assertEqual(self.names(q="yesha"), [])

    def test_filters(self):
        self.assertEqual(self.names(batch=self.a["other_batch"].pk), ["Bilal Ahmed"])
        self.assertEqual(self.names(semester=self.a["semester"].pk), ["Ayesha Khan"])
        self.assertEqual(self.names(section=self.a["other_section"].pk), ["Bilal Ahmed"])
        User.objects.filter(pk=self.other.pk).update(is_active=False)
        self.assertEqual(self.names(status="inactive"), ["Bilal Ahmed"])
        self.assertEqual(self.names(status="active"), ["Ayesha Khan"])

    def test_invalid_filter_is_ignored(self):
        self.assertEqual(len(self.names(batch="999999", status="nope", sort="nope")), 2)

    def test_sorting(self):
        self.assertEqual(self.names(), ["Ayesha Khan", "Bilal Ahmed"])
        self.assertEqual(self.names(sort="sap"), ["Ayesha Khan", "Bilal Ahmed"])
        self.assertEqual(self.names(sort="cohort"), ["Ayesha Khan", "Bilal Ahmed"])
        User.objects.filter(pk=self.student.pk).update(full_name="Zara Khan")
        self.assertEqual(self.names(), ["Bilal Ahmed", "Zara Khan"])
        self.assertEqual(self.names(sort="sap"), ["Zara Khan", "Bilal Ahmed"])

    def test_stats_and_rep_filter(self):
        self.represented_cohort()
        response = self.client.get(self.list_url)
        stats = {s["label"]: s["value"] for s in response.context["stats"]}
        self.assertEqual(stats, {"Total": 5, "Active": 5, "CR/GR": 2, "Inactive": 0})
        self.assertEqual(self.names(status="rep"), ["Ayesha Khan", "Sara Noor"])

    def test_unregistered_account_is_listed(self):
        User.objects.create_user(email=sap(30000003), full_name="New Person")
        self.assertEqual(self.names(status="unregistered"), ["New Person"])

    def test_add_student_account(self):
        response = self.client.post(self.list_url, {"full_name": "New Person", "email": sap(30000003)})
        user = User.objects.get(email=sap(30000003))
        self.assertRedirects(response, self.detail(user))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role, User.Role.STUDENT)

    def test_add_student_refuses_a_non_student_email(self):
        response = self.client.post(self.list_url, {"full_name": "X", "email": "someone@uol.edu.pk"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="someone@uol.edu.pk").exists())


class DetailTests(StudentPagesBase):
    def test_page_shows_identity_and_no_editable_sap_or_email(self):
        response = self.client.get(self.detail())
        self.assertContains(response, "10000001")
        self.assertNotContains(response, 'name="sap_id"')
        self.assertNotContains(response, 'name="email"')

    def test_sap_and_email_can_not_be_posted(self):
        self.edit(sap_id="99999999", email="x@uol.edu.pk", full_name="Ayesha K")
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, sap(10000001))
        self.assertEqual(self.student.student_profile.sap_id, "10000001")
        self.assertEqual(self.student.full_name, "Ayesha K")

    def test_edit_is_audited(self):
        response = self.edit(full_name="Ayesha Malik", section=self.a["other_section"].pk)
        self.assertRedirects(response, self.detail())
        changes = {c.field_name: (c.old_value, c.new_value, c.changed_by_id) for c in StudentProfileChange.objects.all()}
        self.assertEqual(changes, {
            "full_name": ("Ayesha Khan", "Ayesha Malik", self.admin.pk),
            "section": ("Section A", "Section B", self.admin.pk),
        })
        self.assertContains(self.client.get(self.detail()), "Ayesha Malik")

    def test_no_change_writes_no_audit(self):
        self.edit()
        self.assertFalse(StudentProfileChange.objects.exists())

    def test_blank_name_refused(self):
        self.assertEqual(self.edit(full_name="   ").status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "Ayesha Khan")

    def test_only_active_entries_are_offered(self):
        Section.objects.filter(pk=self.a["other_section"].pk).update(is_active=False)
        form = self.client.get(self.detail()).context["edit_form"]
        self.assertNotIn(self.a["other_section"], form.fields["section"].queryset)

    def test_a_current_inactive_entry_stays_selectable_for_a_name_edit(self):
        Section.objects.filter(pk=self.a["section"].pk).update(is_active=False)
        self.assertEqual(self.edit(full_name="Ayesha Noor").status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "Ayesha Noor")

    def test_moving_to_an_inactive_entry_is_refused(self):
        Section.objects.filter(pk=self.a["other_section"].pk).update(is_active=False)
        self.assertEqual(self.edit(section=self.a["other_section"].pk).status_code, 400)
        self.assertEqual(self.student.student_profile.section_id, self.a["section"].pk)

    def test_cr_move_without_replacement_is_refused_with_a_message(self):
        self.represented_cohort()
        response = self.edit(section=self.a["other_section"].pk)
        self.assertContains(response, "leave the post vacant", status_code=400)
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.section_id, self.a["section"].pk)
        self.assertFalse(StudentProfileChange.objects.exists())

    def test_cr_move_with_replacement_keeps_the_post_filled(self):
        _, gr, spare = self.represented_cohort()
        response = self.edit(section=self.a["other_section"].pk, replacement=spare.pk)
        self.assertRedirects(response, self.detail())
        period = CohortRepresentation.objects.current().get()
        self.assertEqual((period.cr_id, period.gr_id), (spare.pk, gr.pk))

    def test_name_edit_of_a_cr_needs_no_replacement(self):
        self.represented_cohort()
        self.assertEqual(self.edit(full_name="Ayesha Noor").status_code, 302)

    def test_edit_name_of_unregistered_account(self):
        user = User.objects.create_user(email=sap(30000003), full_name="Old")
        response = self.client.post(reverse("super_admin_student_edit", args=[user.pk]), {"full_name": "New"})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.full_name, "New")


class ActiveStateTests(StudentPagesBase):
    def test_deactivate_signs_out_on_next_request_and_keeps_the_record(self):
        student_client = self.client_class()
        student_client.force_login(self.student)
        self.assertEqual(student_client.get(reverse("student_home")).status_code, 200)
        self.assertRedirects(self.set_active(self.student, False), self.detail())
        self.assertEqual(student_client.get(reverse("student_home")).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.student.pk, is_active=False).exists())

    def test_reactivate(self):
        self.set_active(self.student, False)
        self.set_active(self.student, True)
        self.assertTrue(User.objects.get(pk=self.student.pk).is_active)

    def test_a_repeated_submit_does_not_flip_the_account_back(self):
        self.set_active(self.student, False)
        self.set_active(self.student, False)
        self.assertFalse(User.objects.get(pk=self.student.pk).is_active)

    def test_cr_deactivation_without_replacement_is_refused(self):
        self.represented_cohort()
        response = self.set_active(self.student, False)
        self.assertContains(response, "leave the post vacant", status_code=400)
        self.assertTrue(User.objects.get(pk=self.student.pk).is_active)

    def test_cr_deactivation_with_replacement(self):
        _, gr, spare = self.represented_cohort()
        self.assertEqual(self.set_active(self.student, False, replacement=spare.pk).status_code, 302)
        period = CohortRepresentation.objects.current().get()
        self.assertEqual((period.cr_id, period.gr_id), (spare.pk, gr.pk))


class ChangeLogTests(StudentPagesBase):
    def test_lists_and_filters_changes(self):
        self.edit(full_name="Ayesha Malik", section=self.a["other_section"].pk)
        url = reverse("super_admin_student_changes")
        self.assertEqual(len(self.client.get(url).context["page"]), 2)
        self.assertEqual(len(self.client.get(url, {"field": "section"}).context["page"]), 1)
        self.assertEqual(len(self.client.get(url, {"q": "2000"}).context["page"]), 0)
