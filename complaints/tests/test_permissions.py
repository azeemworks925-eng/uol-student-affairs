from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import TestCase

from complaints.permissions import (
    can_manage_complaint,
    can_view_complaint,
    get_visible_complaint,
    visible_complaints,
)

from .helpers import (
    OTHER_STUDENT_EMAIL,
    cohort,
    make_academics,
    make_advisor,
    make_categories,
    make_student,
    make_super_admin,
    submit,
)


class ComplaintVisibilityTests(TestCase):
    """DEC-229 and DEC-205: own complaints for students, exact cohorts for advisors."""

    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        category = make_categories()["academic"]
        cls.home = cohort(a)  # Fall 2024 · Semester 4 · Section A
        cls.student = make_student(academics=a)
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=a)
        # Same semester and section, different batch: a partial match.
        cls.other_batch_student = make_student(
            "22223333@student.uol.edu.pk", academics=a, cohort=cohort(a, batch="other_batch")
        )
        cls.other_section_student = make_student(
            "44445555@student.uol.edu.pk", academics=a, cohort=cohort(a, section="other_section")
        )
        cls.mine = submit(cls.student, category)
        cls.classmates = submit(cls.classmate, category)
        cls.other_batch = submit(cls.other_batch_student, category)
        cls.other_section = submit(cls.other_section_student, category)

        cls.advisor = make_advisor(cohorts=[cls.home])
        cls.co_advisor = make_advisor("coadvisor@uol.edu.pk", cohorts=[cls.home])
        cls.unassigned = make_advisor("unassigned@uol.edu.pk")
        # Holds every part of the home cohort, but never all three together.
        cls.partial = make_advisor(
            "partial@uol.edu.pk",
            cohorts=[cohort(a, batch="other_batch"), cohort(a, semester="other_semester"), cohort(a, section="other_section")],
        )
        cls.admin = make_super_admin()

    def visible(self, user):
        return set(visible_complaints(user))

    def test_student_sees_only_their_own_complaints(self):
        self.assertEqual(self.visible(self.student), {self.mine})
        self.assertTrue(can_view_complaint(self.student, self.mine))
        # Being in the same cohort grants a student nothing.
        self.assertFalse(can_view_complaint(self.student, self.classmates))

    def test_student_cannot_reach_another_complaint_by_changing_the_reference(self):
        self.assertEqual(get_visible_complaint(self.student, self.mine.reference), self.mine)
        for other in (self.classmates, self.other_batch):
            with self.subTest(reference=other.reference), self.assertRaises(Http404):
                get_visible_complaint(self.student, other.reference)
        self.assertFalse(visible_complaints(self.student).filter(pk=self.classmates.pk).exists())

    def test_advisor_sees_the_exactly_assigned_cohort(self):
        self.assertEqual(self.visible(self.advisor), {self.mine, self.classmates})
        self.assertTrue(can_view_complaint(self.advisor, self.mine))
        self.assertTrue(can_manage_complaint(self.advisor, self.mine))
        self.assertEqual(get_visible_complaint(self.advisor, self.classmates.reference), self.classmates)

    def test_same_semester_and_section_in_another_batch_is_not_visible(self):
        self.assertNotIn(self.other_batch, self.visible(self.advisor))
        self.assertFalse(can_view_complaint(self.advisor, self.other_batch))
        self.assertFalse(can_manage_complaint(self.advisor, self.other_batch))
        with self.assertRaises(Http404):
            get_visible_complaint(self.advisor, self.other_batch.reference)

    def test_partial_matches_grant_nothing(self):
        self.assertNotIn(self.mine, self.visible(self.partial))
        self.assertFalse(can_view_complaint(self.partial, self.mine))
        self.assertFalse(can_manage_complaint(self.partial, self.mine))

    def test_unassigned_advisor_sees_nothing(self):
        self.assertEqual(self.visible(self.unassigned), set())
        self.assertFalse(can_view_complaint(self.unassigned, self.mine))
        self.assertFalse(can_manage_complaint(self.unassigned, self.mine))

    def test_advisors_sharing_a_cohort_get_the_same_access(self):
        self.assertEqual(self.visible(self.co_advisor), self.visible(self.advisor))
        self.assertTrue(can_manage_complaint(self.co_advisor, self.mine))

    def test_super_admin_sees_every_complaint(self):
        everything = {self.mine, self.classmates, self.other_batch, self.other_section}
        self.assertEqual(self.visible(self.admin), everything)
        self.assertTrue(all(can_manage_complaint(self.admin, c) for c in everything))

    def test_anonymous_and_inactive_users_see_nothing(self):
        self.assertEqual(self.visible(AnonymousUser()), set())
        self.assertFalse(can_view_complaint(AnonymousUser(), self.mine))
        for user in (self.student, self.advisor, self.admin):
            user.is_active = False
            with self.subTest(user=user.email):
                self.assertEqual(self.visible(user), set())
                self.assertFalse(can_view_complaint(user, self.mine))
                self.assertFalse(can_manage_complaint(user, self.mine))

    def test_access_follows_the_complaints_cohort_not_the_students_current_profile(self):
        # The student later moves to another section; the complaint keeps its cohort.
        profile = self.student.student_profile
        profile.section = self.academics["other_section"]
        profile.save()
        self.assertIn(self.mine, self.visible(self.advisor))
        self.assertEqual(self.visible(self.student), {self.mine})

    def test_assignment_changes_take_effect_immediately(self):
        self.advisor.advisor_assignments.all().delete()
        self.assertEqual(self.visible(self.advisor), set())
        self.assertFalse(can_manage_complaint(self.advisor, self.mine))
