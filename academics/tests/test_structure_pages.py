"""Academic Structure page and its services (DEC-330)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from academics import services
from academics.models import Batch, Section, Semester
from accounts.forms import StudentRegistrationForm
from accounts.people_forms import AssignmentForm, active_cohort_choices
from accounts.representation import Cohort, appoint_representatives
from accounts.tests.helpers import make_academics, make_advisor, make_student, make_super_admin
from complaints.models import Complaint, ComplaintCategory, ComplaintStatus


class StructureBase(TestCase):
    def setUp(self):
        self.a = make_academics()
        self.admin = make_super_admin()
        self.client.force_login(self.admin)
        self.url = reverse("super_admin_structure")

    def post_add(self, kind, value):
        return self.client.post(reverse("super_admin_structure_add", args=[kind]), {"value": value})

    def post_edit(self, kind, entry, value):
        return self.client.post(reverse("super_admin_structure_edit", args=[kind, entry.pk]), {"value": value})

    def post_active(self, kind, entry, active):
        return self.client.post(reverse("super_admin_structure_active", args=[kind, entry.pk]), {"active": "1" if active else "0"})


class PermissionTests(StructureBase):
    def test_other_roles_get_404(self):
        student = make_student(academics=self.a)
        advisor = make_advisor()
        posts = [reverse("super_admin_structure_add", args=["batch"]),
                 reverse("super_admin_structure_edit", args=["batch", self.a["batch"].pk]),
                 reverse("super_admin_structure_active", args=["batch", self.a["batch"].pk])]
        for user in (student, advisor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            for url in posts:
                self.assertEqual(self.client.post(url, {"value": "Hacked", "active": "0"}).status_code, 404)
        self.a["batch"].refresh_from_db()
        self.assertEqual(self.a["batch"].name, "Fall 2024")
        self.assertTrue(self.a["batch"].is_active)

    def test_unknown_kind_is_404(self):
        self.assertEqual(self.post_add("department", "X").status_code, 404)


class EntryTests(StructureBase):
    def test_add_each_kind(self):
        self.assertRedirects(self.post_add("batch", "  Fall   2026 "), self.url)
        self.assertTrue(Batch.objects.filter(name="Fall 2026", is_active=True).exists())
        self.assertEqual(self.post_add("semester", "6").status_code, 302)
        self.assertTrue(Semester.objects.filter(number=6).exists())
        self.assertEqual(self.post_add("section", "C").status_code, 302)
        self.assertTrue(Section.objects.filter(name="C").exists())

    def test_invalid_values_are_refused(self):
        self.assertEqual(self.post_add("batch", "   ").status_code, 400)
        self.assertEqual(self.post_add("batch", "Fall 2024").status_code, 400)
        self.assertEqual(self.post_add("semester", "0").status_code, 400)
        self.assertEqual(self.post_add("semester", "4").status_code, 400)
        self.assertEqual(self.post_add("section", "X" * 21).status_code, 400)
        self.assertEqual(Batch.objects.count(), 2)

    def test_a_refused_add_reopens_its_dialog(self):
        response = self.post_add("section", "A")
        self.assertContains(response, 'id="dialog-add-section" aria-labelledby="add-section" data-open-on-load', status_code=400)

    def test_edit_each_kind(self):
        self.assertEqual(self.post_edit("batch", self.a["batch"], "Fall 2024 Morning").status_code, 302)
        self.assertEqual(self.post_edit("semester", self.a["semester"], "7").status_code, 302)
        self.assertEqual(self.post_edit("section", self.a["section"], "Z").status_code, 302)
        for key, field, value in (("batch", "name", "Fall 2024 Morning"), ("semester", "number", 7), ("section", "name", "Z")):
            self.a[key].refresh_from_db()
            self.assertEqual(getattr(self.a[key], field), value)

    def test_edit_refuses_a_duplicate_and_keeps_the_value(self):
        self.assertEqual(self.post_edit("section", self.a["section"], "B").status_code, 400)
        self.a["section"].refresh_from_db()
        self.assertEqual(self.a["section"].name, "A")

    def test_deactivate_and_reactivate_never_delete(self):
        for kind, key, model in (("batch", "batch", Batch), ("semester", "semester", Semester), ("section", "section", Section)):
            count = model.objects.count()
            self.post_active(kind, self.a[key], False)
            self.assertFalse(model.objects.get(pk=self.a[key].pk).is_active)
            self.post_active(kind, self.a[key], True)
            self.assertTrue(model.objects.get(pk=self.a[key].pk).is_active)
            self.assertEqual(model.objects.count(), count)

    def test_there_is_no_delete_route(self):
        self.assertEqual(self.client.post(self.url + "batch/1/delete/").status_code, 404)

    def test_deactivated_section_keeps_its_students(self):
        student = make_student(academics=self.a)
        self.post_active("section", self.a["section"], False)
        student.student_profile.refresh_from_db()
        self.assertEqual(student.student_profile.section_id, self.a["section"].pk)

    def test_deactivating_a_represented_cohort_keeps_the_period(self):
        cr = make_student("10000001@student.uol.edu.pk", academics=self.a)
        gr = make_student("10000002@student.uol.edu.pk", academics=self.a)
        cohort = Cohort(self.a["batch"].pk, self.a["semester"].pk, self.a["section"].pk)
        period = appoint_representatives(self.admin, cohort, cr=cr, gr=gr)
        self.assertEqual(self.post_active("section", self.a["section"], False).status_code, 302)
        period.refresh_from_db()
        self.assertTrue(period.is_active)

    def test_inactive_entries_leave_registration_and_assignment_choices(self):
        self.post_active("section", self.a["other_section"], False)
        self.assertNotIn(self.a["other_section"], StudentRegistrationForm().fields["section"].queryset)
        self.assertNotIn(self.a["other_section"], AssignmentForm().fields["section"].queryset)
        self.assertFalse([label for _, label in active_cohort_choices() if "Section B" in label])

    def test_inactive_entries_stay_listed_and_labelled(self):
        self.post_active("section", self.a["other_section"], False)
        response = self.client.get(self.url)
        self.assertContains(response, "Section B")
        self.assertContains(response, "Inactive")
        self.assertContains(response, "Reactivate")

    def test_service_refuses_a_duplicate(self):
        with self.assertRaises(ValidationError):
            services.create_entry(Section, "A")


class TreeTests(StructureBase):
    def test_page_renders_dfs_totals(self):
        one = make_student("10000001@student.uol.edu.pk", academics=self.a)
        make_student("10000002@student.uol.edu.pk", academics=self.a)
        inactive = make_student("10000003@student.uol.edu.pk", academics=self.a)
        type(inactive).objects.filter(pk=inactive.pk).update(is_active=False)
        category, _ = ComplaintCategory.objects.get_or_create(name="Academic")
        for status in (ComplaintStatus.RECEIVED, ComplaintStatus.RESOLVED):
            Complaint.objects.bulk_create([Complaint(
                reference=f"CMP-2026-{status[:3]}", student=one, batch=self.a["batch"], semester=self.a["semester"],
                section=self.a["section"], category=category, title="A title", description="A description", status=status)])
        response = self.client.get(self.url)
        root = response.context["tree"]
        self.assertEqual((root.label, root.students, root.active_students, root.open_complaints),
                         ("Software Engineering", 3, 2, 1))
        section = root.children[0].children[0].children[0]
        self.assertEqual((section.label, section.students, section.active_students, section.open_complaints),
                         ("Section A", 3, 2, 1))
        self.assertContains(response, "How this is built")
        self.assertContains(response, "<b>3</b> students", html=False)

    def test_tree_shows_only_real_cohorts(self):
        make_student(academics=self.a)
        root = self.client.get(self.url).context["tree"]
        self.assertEqual([child.label for child in root.children], ["Fall 2024"])

    def test_empty_department(self):
        self.assertContains(self.client.get(self.url), "No cohorts yet.")

    def test_inactive_node_is_marked(self):
        make_student(academics=self.a)
        self.post_active("batch", self.a["batch"], False)
        root = self.client.get(self.url).context["tree"]
        self.assertTrue(root.children[0].inactive)
