from django.test import TestCase
from django.urls import reverse

from academics.models import Section
from accounts.models import StudentProfile

from .helpers import make_academics, make_advisor, make_student


class StudentRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()

    def setUp(self):
        self.student = make_student(full_name="")
        self.client.force_login(self.student)

    def registration_data(self, **overrides):
        data = {
            "full_name": "  Ali Khan  ",
            "batch": self.academics["batch"].pk,
            "semester": self.academics["semester"].pk,
            "section": self.academics["section"].pk,
        }
        data.update(overrides)
        return data

    def test_unregistered_student_is_sent_to_registration_from_any_page(self):
        for name in ("home", "student_home", "advisor_home", "super_admin_home"):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(reverse(name)), reverse("student_register"))

    def test_registration_creates_profile_with_sap_id_from_email(self):
        response = self.client.post(reverse("student_register"), self.registration_data())

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        profile = StudentProfile.objects.get(user=self.student)
        self.assertEqual(profile.sap_id, "12345678")
        self.assertEqual(profile.department, "Software Engineering")
        self.assertEqual(profile.section, self.academics["section"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "Ali Khan")
        self.assertEqual(self.client.get(reverse("student_home")).status_code, 200)

    def test_full_name_and_all_academic_fields_are_required(self):
        for field in ("full_name", "batch", "semester", "section"):
            with self.subTest(field=field):
                response = self.client.post(reverse("student_register"), self.registration_data(**{field: ""}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(StudentProfile.objects.exists())

    def test_inactive_academic_entries_cannot_be_chosen(self):
        Section.objects.filter(pk=self.academics["section"].pk).update(is_active=False)

        response = self.client.post(reverse("student_register"), self.registration_data())

        self.assertIn("section", response.context["form"].errors)
        self.assertFalse(StudentProfile.objects.exists())
        self.assertNotContains(self.client.get(reverse("student_register")), "Section A")

    def test_sap_id_cannot_be_supplied_by_the_student(self):
        self.client.post(reverse("student_register"), self.registration_data(sap_id="99999999"))
        self.assertEqual(StudentProfile.objects.get().sap_id, "12345678")

    def test_registration_is_one_time(self):
        self.client.post(reverse("student_register"), self.registration_data())

        response = self.client.post(
            reverse("student_register"),
            self.registration_data(full_name="Changed", section=self.academics["other_section"].pk),
        )

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        profile = StudentProfile.objects.get()
        self.assertEqual(profile.section, self.academics["section"])
        self.assertEqual(profile.user.full_name, "Ali Khan")

    def test_unregistered_student_can_still_sign_out(self):
        self.client.post(reverse("account_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class RegistrationAccessTests(TestCase):
    def test_staff_cannot_use_student_registration(self):
        self.client.force_login(make_advisor())
        self.assertEqual(self.client.get(reverse("student_register")).status_code, 403)

    def test_anonymous_user_is_sent_to_sign_in(self):
        response = self.client.get(reverse("student_register"))
        self.assertRedirects(response, f"{reverse('account_login')}?next={reverse('student_register')}")
