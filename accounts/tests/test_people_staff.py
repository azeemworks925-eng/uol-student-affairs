"""Staff pages for the Super Admin (DEC-330)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import Section
from accounts.models import AdvisorAssignment, User
from accounts.representation import Cohort

from .helpers import make_academics, make_advisor, make_student, make_super_admin

DEMO_EMAIL = "someone.demo@gmail.com"


class StaffBase(TestCase):
    def setUp(self):
        self.a = make_academics()
        self.admin = make_super_admin()
        self.cohort = (self.a["batch"], self.a["semester"], self.a["section"])
        self.advisor = make_advisor(cohorts=[self.cohort])
        self.student = make_student(academics=self.a)
        self.client.force_login(self.admin)
        self.url = reverse("super_admin_staff")

    def key(self, batch="batch", semester="semester", section="section"):
        return Cohort(self.a[batch].pk, self.a[semester].pk, self.a[section].pk).key

    def add(self, email, role=User.Role.BATCH_ADVISOR, cohorts=(), name="New Person"):
        return self.client.post(self.url, {"role": role, "full_name": name, "email": email, "cohorts": list(cohorts)})

    def detail(self, user=None):
        return reverse("super_admin_staff_detail", args=[(user or self.advisor).pk])

    def assign(self, advisor=None, batch="batch", semester="semester", section="other_section"):
        advisor = advisor or self.advisor
        return self.client.post(reverse("super_admin_staff_assignment_add", args=[advisor.pk]), {
            "batch": self.a[batch].pk, "semester": self.a[semester].pk, "section": self.a[section].pk})

    def set_active(self, user, active):
        return self.client.post(reverse("super_admin_staff_active", args=[user.pk]), {"active": "1" if active else "0"})


class PermissionTests(StaffBase):
    def test_other_roles_get_404(self):
        assignment = self.advisor.advisor_assignments.get()
        gets = [self.url, self.detail()]
        posts = [self.url, reverse("super_admin_staff_name", args=[self.advisor.pk]),
                 reverse("super_admin_staff_active", args=[self.advisor.pk]),
                 reverse("super_admin_staff_assignment_add", args=[self.advisor.pk]),
                 reverse("super_admin_staff_assignment_remove", args=[self.advisor.pk, assignment.pk])]
        for user in (self.student, self.advisor):
            self.client.force_login(user)
            for url in gets:
                self.assertEqual(self.client.get(url).status_code, 404, url)
            for url in posts:
                self.assertEqual(self.client.post(url, {"active": "0"}).status_code, 404, url)
        self.assertTrue(AdvisorAssignment.objects.filter(pk=assignment.pk).exists())

    def test_a_student_id_is_not_a_staff_page(self):
        self.assertEqual(self.client.get(self.detail(self.student)).status_code, 404)


class ListTests(StaffBase):
    def names(self, **query):
        return [row.name for row in self.client.get(self.url, query).context["page"]]

    def test_tabs_search_and_filters(self):
        make_advisor("other@uol.edu.pk", full_name="Zainab Ali")
        self.assertEqual(self.names(), ["Test Advisor", "Zainab Ali"])
        self.assertEqual(self.names(q="zain"), ["Zainab Ali"])
        self.assertEqual(self.names(q="other@"), ["Zainab Ali"])
        self.assertEqual(self.names(tab="admins"), ["Head of Batch Advisors"])
        User.objects.filter(email="other@uol.edu.pk").update(is_active=False)
        self.assertEqual(self.names(status="inactive"), ["Zainab Ali"])

    def test_stats_show_coverage(self):
        make_student("20000002@student.uol.edu.pk", academics=self.a,
                     cohort=(self.a["other_batch"], self.a["other_semester"], self.a["other_section"]))
        response = self.client.get(self.url)
        stats = {s["label"]: s["value"] for s in response.context["stats"]}
        self.assertEqual(stats, {"Batch Advisors": 1, "Active": 1, "Cohorts covered": 1, "Cohorts without an advisor": 1})
        self.assertContains(response, "Spring 2025 · Semester 5 · Section B")

    def test_a_deactivated_advisor_does_not_cover_a_cohort(self):
        User.objects.filter(pk=self.advisor.pk).update(is_active=False)
        stats = {s["label"]: s["value"] for s in self.client.get(self.url).context["stats"]}
        self.assertEqual((stats["Cohorts covered"], stats["Cohorts without an advisor"]), (0, 1))

    def test_new_menu_target_opens_the_dialog(self):
        response = self.client.get(self.url, {"new": "1"})
        self.assertContains(response, 'id="dialog-add-staff" aria-labelledby="add-staff-title" data-open-on-load')


class AddStaffTests(StaffBase):
    def test_add_advisor_with_cohorts(self):
        response = self.add("new@uol.edu.pk", cohorts=[self.key(), self.key(section="other_section")])
        user = User.objects.get(email="new@uol.edu.pk")
        self.assertRedirects(response, self.detail(user))
        self.assertEqual(user.role, User.Role.BATCH_ADVISOR)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.advisor_assignments.count(), 2)
        self.assertEqual(user.advisor_assignments.first().assigned_by, self.admin)

    def test_invalid_domains_are_refused(self):
        for email in ("x@gmail.com", "12345670@student.uol.edu.pk"):
            self.assertEqual(self.add(email).status_code, 400, email)
            self.assertFalse(User.objects.filter(email=email).exists())

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[DEMO_EMAIL])
    def test_demo_email_is_allowed_in_debug(self):
        self.assertEqual(self.add(DEMO_EMAIL).status_code, 302)

    @override_settings(DEBUG=False, DEMO_STAFF_EMAILS=[DEMO_EMAIL])
    def test_demo_email_is_refused_outside_debug(self):
        self.assertEqual(self.add(DEMO_EMAIL).status_code, 400)
        self.assertFalse(User.objects.filter(email=DEMO_EMAIL).exists())

    def test_duplicate_email_refused(self):
        self.assertEqual(self.add(self.advisor.email).status_code, 400)

    def test_inactive_cohort_can_not_be_chosen_and_nothing_is_created(self):
        Section.objects.filter(pk=self.a["other_section"].pk).update(is_active=False)
        self.assertEqual(self.add("new@uol.edu.pk", cohorts=[self.key(section="other_section")]).status_code, 400)
        self.assertFalse(User.objects.filter(email="new@uol.edu.pk").exists())

    def test_add_super_admin(self):
        self.assertEqual(self.add("second@uol.edu.pk", role=User.Role.SUPER_ADMIN).status_code, 302)
        user = User.objects.get(email="second@uol.edu.pk")
        self.assertTrue(user.is_super_admin and user.is_staff)
        self.assertEqual(user.advisor_assignments.count(), 0)

    def test_add_super_admin_keeps_the_staff_email_rule(self):
        self.assertEqual(self.add("x@gmail.com", role=User.Role.SUPER_ADMIN).status_code, 400)


class AssignmentTests(StaffBase):
    def remove(self, assignment, advisor=None):
        advisor = advisor or self.advisor
        return self.client.post(reverse("super_admin_staff_assignment_remove", args=[advisor.pk, assignment.pk]), follow=True)

    def test_add_exact_cohort(self):
        self.assertRedirects(self.assign(), self.detail())
        self.assertTrue(self.advisor.advisor_assignments.filter(section=self.a["other_section"], assigned_by=self.admin).exists())

    def test_duplicate_refused(self):
        self.assertContains(self.assign(section="section"), "already assigned", status_code=400)
        self.assertEqual(self.advisor.advisor_assignments.count(), 1)

    def test_inactive_entry_refused(self):
        Section.objects.filter(pk=self.a["other_section"].pk).update(is_active=False)
        self.assertEqual(self.assign().status_code, 400)

    def test_inactive_advisor_refused(self):
        User.objects.filter(pk=self.advisor.pk).update(is_active=False)
        self.assertContains(self.assign(), "Reactivate", status_code=400)

    def test_removing_the_last_advisor_warns_but_works(self):
        assignment = self.advisor.advisor_assignments.get()
        self.assertContains(self.remove(assignment), "now has no active advisor")
        self.assertFalse(AdvisorAssignment.objects.filter(pk=assignment.pk).exists())

    def test_removing_a_shared_cohort_does_not_warn(self):
        make_advisor("other@uol.edu.pk", cohorts=[self.cohort])
        self.assertNotContains(self.remove(self.advisor.advisor_assignments.get()), "now has no active advisor")

    def test_only_active_other_advisors_count_as_cover(self):
        other = make_advisor("other@uol.edu.pk", cohorts=[self.cohort])
        User.objects.filter(pk=other.pk).update(is_active=False)
        self.assertContains(self.remove(self.advisor.advisor_assignments.get()), "now has no active advisor")

    def test_another_advisors_assignment_can_not_be_removed_through_this_url(self):
        other = make_advisor("other@uol.edu.pk", cohorts=[self.cohort])
        assignment = other.advisor_assignments.get()
        self.remove(assignment)
        self.assertTrue(AdvisorAssignment.objects.filter(pk=assignment.pk).exists())


class AccountTests(StaffBase):
    def test_edit_name(self):
        self.client.post(reverse("super_admin_staff_name", args=[self.advisor.pk]), {"full_name": "  Dr.  Sana  Mir "})
        self.advisor.refresh_from_db()
        self.assertEqual(self.advisor.full_name, "Dr. Sana Mir")

    def test_deactivate_and_reactivate_advisor_keeps_assignments(self):
        self.assertEqual(self.set_active(self.advisor, False).status_code, 302)
        self.assertFalse(User.objects.get(pk=self.advisor.pk).is_active)
        self.assertEqual(self.advisor.advisor_assignments.count(), 1)
        self.set_active(self.advisor, True)
        self.assertTrue(User.objects.get(pk=self.advisor.pk).is_active)

    def test_last_active_super_admin_is_refused_and_explained(self):
        self.assertContains(self.client.get(self.detail(self.admin)), "last active Super Admin")
        response = self.set_active(self.admin, False)
        self.assertContains(response, "The last active Super Admin cannot be deactivated.", status_code=400)
        self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)

    def test_a_super_admin_can_be_deactivated_when_another_is_active(self):
        second = make_super_admin("second@uol.edu.pk")
        self.assertEqual(self.set_active(second, False).status_code, 302)
        self.assertFalse(User.objects.get(pk=second.pk).is_active)

    def test_detail_renders_for_both_roles(self):
        self.assertContains(self.client.get(self.detail()), "Coverage")
        self.assertContains(self.client.get(self.detail(self.admin)), "Super Admin access")
