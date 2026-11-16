from django.contrib.auth import aauthenticate, authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from accounts import identity
from accounts.models import AdvisorAssignment, StudentProfile, User

from .helpers import (
    ADVISOR_EMAIL,
    OTHER_ADVISOR_EMAIL,
    STUDENT_EMAIL,
    cohort,
    make_academics,
    make_advisor,
    make_student,
)

PASSWORD = "Str0ng-test-pass!"


class IdentityRuleTests(TestCase):
    def test_extracts_sap_id_from_valid_student_email(self):
        self.assertEqual(identity.extract_sap_id("12345678@student.uol.edu.pk"), "12345678")
        self.assertEqual(identity.extract_sap_id("  12345678@STUDENT.UOL.EDU.PK "), "12345678")

    def test_rejects_invalid_student_emails(self):
        for email in (
            "1234567@student.uol.edu.pk",  # seven digits
            "123456789@student.uol.edu.pk",  # nine digits
            "1234567a@student.uol.edu.pk",
            "ali.khan@student.uol.edu.pk",
            "12345678@uol.edu.pk",
            "12345678@student.uol.edu.pk.example.com",
            "12345678@xstudent.uol.edu.pk",
            "x12345678@student.uol.edu.pk",
            "",
            None,
        ):
            with self.subTest(email=email):
                self.assertIsNone(identity.extract_sap_id(email))
                self.assertFalse(identity.is_student_email(email))

    def test_staff_email_uses_configured_domains_only(self):
        self.assertTrue(identity.is_staff_email("Teacher.Name@UOL.EDU.PK"))
        for email in ("12345678@student.uol.edu.pk", "teacher@gmail.com", "teacher@uol.edu.pk.evil.com", ""):
            with self.subTest(email=email):
                self.assertFalse(identity.is_staff_email(email))

    @override_settings(UOL_STAFF_EMAIL_DOMAINS=["staff.example.edu", "student.uol.edu.pk"])
    def test_student_domain_is_never_a_staff_domain(self):
        self.assertTrue(identity.is_staff_email("t@staff.example.edu"))
        self.assertFalse(identity.is_staff_email("t@uol.edu.pk"))
        self.assertFalse(identity.is_staff_email("12345678@student.uol.edu.pk"))


class UserModelTests(TestCase):
    def test_auth_user_model_is_custom_user(self):
        self.assertIs(get_user_model(), User)

    def test_email_is_the_login_identifier(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, [])
        self.assertFalse(any(f.name == "username" for f in User._meta.get_fields()))

    def test_str_returns_email(self):
        self.assertEqual(str(make_student()), STUDENT_EMAIL)

    def test_full_name_is_used_for_display(self):
        user = make_student(full_name="Ali Khan")
        self.assertEqual(user.get_full_name(), "Ali Khan")
        self.assertEqual(User(email=STUDENT_EMAIL).get_full_name(), STUDENT_EMAIL)

    def test_email_must_be_unique(self):
        make_student()
        with self.assertRaises(ValidationError):
            make_student()

    def test_database_also_enforces_unique_email(self):
        make_student()
        duplicate = User(email=STUDENT_EMAIL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()


class CreateUserTests(TestCase):
    def test_creates_user_with_email_and_hashed_password(self):
        user = User.objects.create_user(email=STUDENT_EMAIL, password=PASSWORD)

        self.assertEqual(user.email, STUDENT_EMAIL)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_defaults_to_active_student_without_admin_flags(self):
        user = User.objects.create_user(email=STUDENT_EMAIL)

        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_without_password_sets_unusable_password(self):
        self.assertFalse(User.objects.create_user(email=STUDENT_EMAIL).has_usable_password())

    def test_requires_email(self):
        for missing in (None, "", "   "):
            with self.subTest(email=missing), self.assertRaisesMessage(
                ValueError, "An email address is required."
            ):
                User.objects.create_user(email=missing, password=PASSWORD)

    def test_accepts_batch_advisor_with_staff_email(self):
        user = User.objects.create_user(email=ADVISOR_EMAIL, role=User.Role.BATCH_ADVISOR)
        self.assertEqual(user.role, User.Role.BATCH_ADVISOR)
        self.assertFalse(user.is_staff)


class ManagerValidationTests(TestCase):
    """Review M2: the manager validates email format, role and the role's email rule."""

    def assert_rejected(self, field, **kwargs):
        with self.assertRaises(ValidationError) as ctx:
            User.objects.create_user(**kwargs)
        self.assertIn(field, ctx.exception.message_dict)
        self.assertFalse(User.objects.exists())

    def test_rejects_malformed_email(self):
        self.assert_rejected("email", email="not-an-email")

    def test_rejects_unknown_role(self):
        self.assert_rejected("role", email=ADVISOR_EMAIL, role="hacker")

    def test_rejects_student_without_sap_id_email(self):
        for email in ("ali.khan@student.uol.edu.pk", "1234567@student.uol.edu.pk", ADVISOR_EMAIL, "s@gmail.com"):
            with self.subTest(email=email):
                self.assert_rejected("email", email=email, role=User.Role.STUDENT)

    def test_rejects_staff_without_staff_email(self):
        for role in User.STAFF_ROLES:
            for email in (STUDENT_EMAIL, "teacher@gmail.com"):
                with self.subTest(role=role, email=email):
                    self.assert_rejected("email", email=email, role=role)


class RoleConsistencyTests(TestCase):
    """Review M1: the role is the single source of truth for is_staff/is_superuser."""

    def test_only_super_admin_holds_admin_flags(self):
        student = User.objects.create_user(email=STUDENT_EMAIL, is_staff=True, is_superuser=True)
        advisor = User.objects.create_user(
            email=ADVISOR_EMAIL, role=User.Role.BATCH_ADVISOR, is_staff=True, is_superuser=True
        )
        head = User.objects.create_user(email="head@uol.edu.pk", role=User.Role.SUPER_ADMIN)

        for user in (student, advisor):
            user.refresh_from_db()
            self.assertEqual((user.is_staff, user.is_superuser), (False, False))
        head.refresh_from_db()
        self.assertEqual((head.is_staff, head.is_superuser), (True, True))

    def test_saving_resynchronizes_tampered_flags(self):
        advisor = make_advisor()
        advisor.is_superuser = True
        advisor.is_staff = True
        advisor.save()
        advisor.refresh_from_db()
        self.assertFalse(advisor.is_superuser)
        self.assertFalse(advisor.is_staff)

    def test_role_helpers(self):
        advisor = make_advisor()
        self.assertTrue(advisor.is_batch_advisor)
        self.assertFalse(advisor.is_student)
        self.assertFalse(advisor.is_super_admin)


class CreateSuperuserTests(TestCase):
    def test_creates_super_admin_with_admin_flags(self):
        user = User.objects.create_superuser(email="admin@uol.edu.pk", password=PASSWORD)

        self.assertEqual(user.role, User.Role.SUPER_ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))

    def test_rejects_any_other_role(self):
        for role in (User.Role.STUDENT, User.Role.BATCH_ADVISOR):
            with self.subTest(role=role), self.assertRaisesMessage(ValueError, "Super Admin role"):
                User.objects.create_superuser(email="admin@uol.edu.pk", role=role)

    def test_rejects_is_staff_false(self):
        with self.assertRaisesMessage(ValueError, "is_staff=True"):
            User.objects.create_superuser(email="admin@uol.edu.pk", password=PASSWORD, is_staff=False)

    def test_rejects_is_superuser_false(self):
        with self.assertRaisesMessage(ValueError, "is_superuser=True"):
            User.objects.create_superuser(email="admin@uol.edu.pk", password=PASSWORD, is_superuser=False)

    def test_requires_email(self):
        with self.assertRaisesMessage(ValueError, "An email address is required."):
            User.objects.create_superuser(email="", password=PASSWORD)

    def test_requires_staff_email(self):
        with self.assertRaises(ValidationError):
            User.objects.create_superuser(email=STUDENT_EMAIL)


class EmailNormalizationTests(TestCase):
    """Emails are lowercased in full on every path, independent of database collation."""

    MIXED = "12345678@Student.UOL.edu.pk"
    NORMALIZED = "12345678@student.uol.edu.pk"

    def test_normalize_email_lowercases_whole_address_and_strips(self):
        for raw in (self.MIXED, "12345678@STUDENT.UOL.EDU.PK", f"  {self.MIXED}  ", self.NORMALIZED):
            with self.subTest(raw=raw):
                self.assertEqual(User.objects.normalize_email(raw), self.NORMALIZED)

    def test_create_user_stores_lowercase_email(self):
        user = User.objects.create_user(email=self.MIXED)
        user.refresh_from_db()
        self.assertEqual(user.email, self.NORMALIZED)

    def test_create_superuser_stores_lowercase_email(self):
        user = User.objects.create_superuser(email="Ali.Khan@UOL.EDU.PK", password=PASSWORD)
        user.refresh_from_db()
        self.assertEqual(user.email, "ali.khan@uol.edu.pk")

    def test_create_user_rejects_case_variant_of_existing_email(self):
        User.objects.create_user(email=self.NORMALIZED)
        with self.assertRaises(ValidationError):
            User.objects.create_user(email=self.MIXED)
        self.assertEqual(User.objects.count(), 1)

    def test_model_clean_lowercases_email(self):
        user = User(email=self.MIXED)
        user.clean()
        self.assertEqual(user.email, self.NORMALIZED)

    def test_full_clean_rejects_case_variant_of_existing_email(self):
        User.objects.create_user(email=self.NORMALIZED)
        user = User(email=self.MIXED)
        user.set_unusable_password()

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn("email", ctx.exception.message_dict)

    def test_full_clean_still_rejects_invalid_email(self):
        user = User(email="Not-An-Email")
        user.set_unusable_password()

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn("email", ctx.exception.message_dict)

    def test_authentication_lookup_ignores_case(self):
        User.objects.create_user(email=self.NORMALIZED, password=PASSWORD)

        self.assertEqual(User.objects.get_by_natural_key(self.MIXED).email, self.NORMALIZED)
        self.assertIsNotNone(authenticate(email=self.MIXED, password=PASSWORD))


class AsyncEmailLookupTests(TestCase):
    MIXED = "12345678@Student.UOL.edu.pk"
    NORMALIZED = "12345678@student.uol.edu.pk"

    @classmethod
    def setUpTestData(cls):
        User.objects.create_user(email=cls.NORMALIZED, password=PASSWORD)

    async def test_async_lookup_ignores_case(self):
        user = await User.objects.aget_by_natural_key(self.MIXED)
        self.assertEqual(user.email, self.NORMALIZED)

    async def test_async_authentication_ignores_case(self):
        user = await aauthenticate(email=self.MIXED, password=PASSWORD)
        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.NORMALIZED)


class StudentProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()

    def test_sap_id_is_derived_from_email_and_department_defaults(self):
        profile = make_student(academics=self.academics).student_profile
        self.assertEqual(profile.sap_id, "12345678")
        self.assertEqual(profile.department, "Software Engineering")

    def test_sap_id_cannot_be_set_independently(self):
        user = make_student()
        profile = StudentProfile(
            user=user, sap_id="99999999", batch=self.academics["batch"],
            semester=self.academics["semester"], section=self.academics["section"],
        )
        profile.save()
        self.assertEqual(profile.sap_id, "12345678")

    def test_only_students_can_have_a_profile(self):
        profile = StudentProfile(
            user=make_advisor(), batch=self.academics["batch"],
            semester=self.academics["semester"], section=self.academics["section"],
        )
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean(exclude=["sap_id"])
        self.assertIn("user", ctx.exception.message_dict)


class AdvisorAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()

    def test_several_advisors_can_share_a_cohort(self):
        batch, semester, section = cohort(self.academics)
        make_advisor(cohorts=[(batch, semester, section)])
        make_advisor(OTHER_ADVISOR_EMAIL, cohorts=[(batch, semester, section)])
        self.assertEqual(
            AdvisorAssignment.objects.filter(batch=batch, semester=semester, section=section).count(), 2
        )

    def test_an_advisor_can_have_several_cohorts(self):
        a = self.academics
        advisor = make_advisor(cohorts=[
            cohort(a),
            cohort(a, batch="other_batch"),  # Same semester and section, different batch.
            cohort(a, semester="other_semester", section="other_section"),
        ])
        self.assertEqual(advisor.advisor_assignments.count(), 3)

    def test_duplicate_cohort_assignment_is_rejected(self):
        batch, semester, section = cohort(self.academics)
        advisor = make_advisor(cohorts=[(batch, semester, section)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            AdvisorAssignment.objects.create(advisor=advisor, batch=batch, semester=semester, section=section)

    def test_batch_is_required(self):
        assignment = AdvisorAssignment(
            advisor=make_advisor(), semester=self.academics["semester"], section=self.academics["section"]
        )
        with self.assertRaises(ValidationError) as ctx:
            assignment.full_clean()
        self.assertIn("batch", ctx.exception.message_dict)

    def test_only_batch_advisors_can_be_assigned(self):
        batch, semester, section = cohort(self.academics)
        assignment = AdvisorAssignment(advisor=make_student(), batch=batch, semester=semester, section=section)
        with self.assertRaises(ValidationError) as ctx:
            assignment.full_clean()
        self.assertIn("advisor", ctx.exception.message_dict)
