from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.permissions import can_access_cohort, visible_student_profiles

from .helpers import (
    OTHER_ADVISOR_EMAIL,
    OTHER_STUDENT_EMAIL,
    cohort,
    make_academics,
    make_advisor,
    make_student,
    make_super_admin,
)

ROLE_PAGES = {
    User.Role.STUDENT: "student_home",
    User.Role.BATCH_ADVISOR: "advisor_home",
    User.Role.SUPER_ADMIN: "super_admin_home",
}


class RoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.users = {
            User.Role.STUDENT: make_student(academics=cls.academics),
            User.Role.BATCH_ADVISOR: make_advisor(),
            User.Role.SUPER_ADMIN: make_super_admin(),
        }

    def test_each_role_reaches_only_its_own_area(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            for page_role, page in ROLE_PAGES.items():
                with self.subTest(user=role, page=page):
                    expected = 200 if page_role == role else 403
                    self.assertEqual(self.client.get(reverse(page)).status_code, expected)

    def test_home_directs_each_role_to_its_area(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                self.assertRedirects(self.client.get(reverse("home")), reverse(ROLE_PAGES[role]))

    def test_request_parameters_cannot_change_access(self):
        self.client.force_login(self.users[User.Role.STUDENT])
        for params in ({"role": "super_admin"}, {"is_superuser": "1"}, {"as": "batch_advisor"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(reverse("super_admin_home"), params).status_code, 403)
                self.assertEqual(self.client.post(reverse("advisor_home"), params).status_code, 403)

    def test_anonymous_users_are_sent_to_sign_in(self):
        for page in [*ROLE_PAGES.values(), "home"]:
            with self.subTest(page=page):
                response = self.client.get(reverse(page))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_only_super_admin_can_open_django_admin(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(reverse("admin:index"))
                if role == User.Role.SUPER_ADMIN:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response["Location"].startswith(reverse("admin:login")))

    def test_admin_password_login_is_replaced_by_google_sign_in(self):
        response = self.client.get(reverse("admin:login"), {"next": "/admin/"})
        self.assertRedirects(response, f"{reverse('account_login')}?next=%2Fadmin%2F", fetch_redirect_response=False)
        response = self.client.post(reverse("admin:login"), {"username": "x", "password": "y"})
        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_admin_login_redirect_ignores_external_next(self):
        response = self.client.get(reverse("admin:login"), {"next": "https://evil.example.com/"})
        self.assertRedirects(response, f"{reverse('account_login')}?next=%2Fadmin%2F", fetch_redirect_response=False)

    def test_deactivated_user_loses_access_immediately(self):
        advisor = self.users[User.Role.BATCH_ADVISOR]
        self.client.force_login(advisor)
        User.objects.filter(pk=advisor.pk).update(is_active=False)

        response = self.client.get(reverse("advisor_home"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))


class CohortScopeTests(TestCase):
    """Advisor access is limited to the exact batch + semester + section combination."""

    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        cls.cohort_a = cohort(a)
        # Every cohort below shares at least one part with cohort_a but is not cohort_a.
        cls.near_misses = {
            "other batch, same semester and section": cohort(a, batch="other_batch"),
            "other semester": cohort(a, semester="other_semester"),
            "other section": cohort(a, section="other_section"),
            "other semester and section": cohort(a, semester="other_semester", section="other_section"),
        }
        cls.student_a = make_student(academics=a, cohort=cls.cohort_a)
        cls.other_batch_student = make_student(
            OTHER_STUDENT_EMAIL, academics=a, cohort=cls.near_misses["other batch, same semester and section"]
        )
        cls.other_section_student = make_student(
            "11112222@student.uol.edu.pk", academics=a, cohort=cls.near_misses["other section"]
        )
        cls.advisor_a = make_advisor(cohorts=[cls.cohort_a])
        cls.co_advisor_a = make_advisor(OTHER_ADVISOR_EMAIL, cohorts=[cls.cohort_a])
        cls.unassigned_advisor = make_advisor("idle@uol.edu.pk")
        cls.head = make_super_admin()

    def visible(self, user):
        return set(visible_student_profiles(user).values_list("user__email", flat=True))

    def test_advisor_sees_only_students_in_the_exact_assigned_cohort(self):
        self.assertEqual(self.visible(self.advisor_a), {self.student_a.email})
        self.assertTrue(can_access_cohort(self.advisor_a, *self.cohort_a))

    def test_partial_cohort_matches_grant_no_access(self):
        for label, near_miss in self.near_misses.items():
            with self.subTest(label):
                self.assertFalse(can_access_cohort(self.advisor_a, *near_miss))

    def test_same_semester_and_section_in_another_batch_is_not_visible(self):
        self.assertNotIn(self.other_batch_student.email, self.visible(self.advisor_a))

    def test_advisor_with_several_cohorts_sees_each_exactly(self):
        a = self.academics
        multi = make_advisor("multi@uol.edu.pk", cohorts=[self.cohort_a, cohort(a, batch="other_batch")])

        self.assertEqual(self.visible(multi), {self.student_a.email, self.other_batch_student.email})
        self.assertTrue(can_access_cohort(multi, *cohort(a, batch="other_batch")))
        self.assertFalse(can_access_cohort(multi, *self.near_misses["other section"]))

    def test_advisors_sharing_a_cohort_see_the_same_students(self):
        self.assertEqual(self.visible(self.co_advisor_a), self.visible(self.advisor_a))
        self.assertTrue(can_access_cohort(self.co_advisor_a, *self.cohort_a))

    def test_unassigned_advisor_sees_nothing(self):
        self.assertEqual(self.visible(self.unassigned_advisor), set())
        self.assertFalse(can_access_cohort(self.unassigned_advisor, *self.cohort_a))

    def test_students_see_only_themselves_and_their_own_cohort(self):
        self.assertEqual(self.visible(self.student_a), {self.student_a.email})
        self.assertTrue(can_access_cohort(self.student_a, *self.cohort_a))
        for label, near_miss in self.near_misses.items():
            with self.subTest(label):
                self.assertFalse(can_access_cohort(self.student_a, *near_miss))

    def test_super_admin_sees_everything(self):
        self.assertEqual(
            self.visible(self.head),
            {self.student_a.email, self.other_batch_student.email, self.other_section_student.email},
        )
        self.assertTrue(can_access_cohort(self.head, *self.near_misses["other batch, same semester and section"]))

    def test_anonymous_and_inactive_users_see_nothing(self):
        self.advisor_a.is_active = False
        for user in (AnonymousUser(), self.advisor_a):
            with self.subTest(user=user):
                self.assertEqual(self.visible(user), set())
                self.assertFalse(can_access_cohort(user, *self.cohort_a))

    def test_changing_assignments_changes_access(self):
        self.advisor_a.advisor_assignments.all().delete()
        self.assertEqual(self.visible(self.advisor_a), set())
        self.assertFalse(can_access_cohort(self.advisor_a, *self.cohort_a))
