"""The Super Admin's interim management interface: staff provisioning and corrections."""

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from accounts.models import AdvisorAssignment, StudentProfileChange, User

from .helpers import (
    ADVISOR_EMAIL,
    STUDENT_EMAIL,
    cohort,
    make_academics,
    make_advisor,
    make_student,
    make_super_admin,
)


class AdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.head = make_super_admin()
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")

    def setUp(self):
        self.client.force_login(self.head)

    def add_user(self, **data):
        return self.client.post(reverse("admin:accounts_user_add"), data)


class UserAdminTests(AdminTestCase):
    def test_user_model_is_registered(self):
        self.assertTrue(admin.site.is_registered(User))

    def test_changelist_searches_by_email_and_filters_by_role(self):
        url = reverse("admin:accounts_user_changelist")

        response = self.client.get(url, {"q": "12345678"})
        self.assertEqual([u.email for u in response.context["cl"].result_list], [STUDENT_EMAIL])

        response = self.client.get(url, {"role__exact": User.Role.SUPER_ADMIN})
        self.assertEqual(list(response.context["cl"].result_list), [self.head])

    def test_accounts_cannot_be_deleted(self):
        response = self.client.get(reverse("admin:accounts_user_delete", args=[self.student.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())

    def test_deactivation_is_a_soft_delete(self):
        response = self.client.post(
            reverse("admin:accounts_user_change", args=[self.student.pk]),
            {"full_name": "Ali Khan"},  # is_active unticked
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertTrue(hasattr(self.student, "student_profile"))


class StaffProvisioningTests(AdminTestCase):
    def test_super_admin_creates_batch_advisor_without_password(self):
        response = self.add_user(email="Teacher.Name@UOL.EDU.PK", full_name="Teacher Name", role=User.Role.BATCH_ADVISOR)

        self.assertEqual(response.status_code, 302)
        advisor = User.objects.get(role=User.Role.BATCH_ADVISOR)
        self.assertEqual(advisor.email, "teacher.name@uol.edu.pk")
        self.assertEqual(advisor.full_name, "Teacher Name")
        self.assertFalse(advisor.has_usable_password())
        self.assertEqual((advisor.is_staff, advisor.is_superuser), (False, False))

    def test_advisor_requires_official_staff_email(self):
        for email in (STUDENT_EMAIL.replace("1", "2"), "teacher@gmail.com", "not-an-email"):
            with self.subTest(email=email):
                response = self.add_user(email=email, full_name="T", role=User.Role.BATCH_ADVISOR)
                self.assertEqual(response.status_code, 200)
                self.assertIn("email", response.context["adminform"].form.errors)
        self.assertFalse(User.objects.filter(role=User.Role.BATCH_ADVISOR).exists())

    def test_case_variant_of_existing_email_is_rejected(self):
        make_advisor()
        response = self.add_user(email=ADVISOR_EMAIL.upper(), full_name="T", role=User.Role.BATCH_ADVISOR)
        self.assertIn("email", response.context["adminform"].form.errors)
        self.assertEqual(User.objects.filter(role=User.Role.BATCH_ADVISOR).count(), 1)

    def test_email_and_role_cannot_be_changed_after_creation(self):
        advisor = make_advisor()
        self.client.post(
            reverse("admin:accounts_user_change", args=[advisor.pk]),
            {"email": "other@uol.edu.pk", "role": User.Role.SUPER_ADMIN, "full_name": "Renamed", "is_active": "on",
             **self.empty_inline()},
        )
        advisor.refresh_from_db()
        self.assertEqual((advisor.email, advisor.role, advisor.full_name), (ADVISOR_EMAIL, User.Role.BATCH_ADVISOR, "Renamed"))
        self.assertFalse(advisor.is_superuser)

    def empty_inline(self, forms=()):
        prefix = "advisor_assignments"
        data = {
            f"{prefix}-TOTAL_FORMS": str(len(forms)),
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
        for i, (batch, semester, section) in enumerate(forms):
            data[f"{prefix}-{i}-batch"] = batch.pk if batch else ""
            data[f"{prefix}-{i}-semester"] = semester.pk
            data[f"{prefix}-{i}-section"] = section.pk
        return data

    def post_assignments(self, advisor, cohorts):
        return self.client.post(
            reverse("admin:accounts_user_change", args=[advisor.pk]),
            {"full_name": "Test Advisor", "is_active": "on", **self.empty_inline(cohorts)},
        )

    def test_super_admin_assigns_cohorts(self):
        advisor = make_advisor()
        a = self.academics
        response = self.post_assignments(advisor, [
            cohort(a),
            cohort(a, batch="other_batch"),
            cohort(a, semester="other_semester", section="other_section"),
        ])

        self.assertEqual(response.status_code, 302)
        assignments = AdvisorAssignment.objects.filter(advisor=advisor)
        self.assertEqual(
            {(x.batch, x.semester, x.section) for x in assignments},
            {cohort(a), cohort(a, batch="other_batch"), cohort(a, semester="other_semester", section="other_section")},
        )
        self.assertTrue(all(x.assigned_by == self.head for x in assignments))

    def test_assignment_without_batch_is_rejected(self):
        advisor = make_advisor()
        response = self.post_assignments(advisor, [(None, self.academics["semester"], self.academics["section"])])

        self.assertEqual(response.status_code, 200)
        self.assertIn("batch", response.context["inline_admin_formsets"][0].formset.errors[0])
        self.assertFalse(AdvisorAssignment.objects.exists())

    def test_duplicate_cohort_in_one_submission_is_rejected(self):
        advisor = make_advisor()
        response = self.post_assignments(advisor, [cohort(self.academics), cohort(self.academics)])

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AdvisorAssignment.objects.exists())

    def test_assignment_inline_is_offered_only_for_batch_advisors(self):
        advisor_page = self.client.get(reverse("admin:accounts_user_change", args=[make_advisor().pk]))
        student_page = self.client.get(reverse("admin:accounts_user_change", args=[self.student.pk]))
        self.assertContains(advisor_page, "advisor_assignments-TOTAL_FORMS")
        self.assertNotContains(student_page, "advisor_assignments-TOTAL_FORMS")


class StudentCorrectionAuditTests(AdminTestCase):
    def test_super_admin_section_change_is_audited(self):
        profile = self.student.student_profile
        a = self.academics
        response = self.client.post(
            reverse("admin:accounts_studentprofile_change", args=[profile.pk]),
            {"batch": a["batch"].pk, "semester": a["other_semester"].pk, "section": a["other_section"].pk},
        )

        self.assertEqual(response.status_code, 302)
        changes = {c.field_name: c for c in StudentProfileChange.objects.filter(profile=profile)}
        self.assertEqual(set(changes), {"semester", "section"})
        self.assertEqual((changes["semester"].old_value, changes["semester"].new_value), ("Semester 4", "Semester 5"))
        self.assertEqual(changes["section"].changed_by, self.head)

    def test_full_name_correction_is_audited(self):
        self.client.post(reverse("admin:accounts_user_change", args=[self.student.pk]),
                         {"full_name": "Ali Raza Khan", "is_active": "on"})

        change = StudentProfileChange.objects.get(field_name="full_name")
        self.assertEqual((change.old_value, change.new_value), ("Ali Khan", "Ali Raza Khan"))

    def test_unchanged_save_records_nothing(self):
        profile = self.student.student_profile
        self.client.post(
            reverse("admin:accounts_studentprofile_change", args=[profile.pk]),
            {"batch": profile.batch_id, "semester": profile.semester_id, "section": profile.section_id},
        )
        self.assertFalse(StudentProfileChange.objects.exists())

    def test_profiles_are_not_created_or_deleted_in_admin_and_audit_is_read_only(self):
        self.assertEqual(self.client.get(reverse("admin:accounts_studentprofile_add")).status_code, 403)
        profile = self.student.student_profile
        self.assertEqual(
            self.client.get(reverse("admin:accounts_studentprofile_delete", args=[profile.pk])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("admin:accounts_studentprofilechange_add")).status_code, 403)
