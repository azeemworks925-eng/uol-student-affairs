import importlib
import re
import threading

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from complaints import services
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent, ComplaintSubcategory

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


class InitialCategoryTests(TestCase):
    def test_initial_categories_are_seeded_as_ordinary_rows(self):
        # Run the data migration's own function on a clean table (a kept test database may
        # have been flushed by a TransactionTestCase). Running it twice adds nothing.
        seed = importlib.import_module("complaints.migrations.0002_initial_categories").add_initial_categories
        ComplaintCategory.objects.all().delete()
        seed(apps, None)
        seed(apps, None)
        names = list(ComplaintCategory.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Academic", "Non-academic", "Personal/Wellbeing", "Other"])
        # Not a fixed list: categories can be added and deactivated like any other row.
        extra = ComplaintCategory.objects.create(name="Transport", position=5)
        ComplaintCategory.objects.filter(name="Other").update(is_active=False)
        active = set(ComplaintCategory.objects.active().values_list("name", flat=True))
        self.assertIn(extra.name, active)
        self.assertNotIn("Other", active)


class SubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.categories = make_categories()
        cls.student = make_student(academics=cls.academics)

    def test_valid_submission(self):
        complaint = submit(
            self.student, self.categories["academic"], subcategory=self.categories["exams"],
            title="  Exam clash  ", description="  Two exams on one day.  ",
        )
        complaint.refresh_from_db()
        self.assertEqual(complaint.student, self.student)
        self.assertEqual(complaint.cohort, cohort(self.academics))
        self.assertEqual(complaint.category, self.categories["academic"])
        self.assertEqual(complaint.subcategory, self.categories["exams"])
        self.assertEqual((complaint.title, complaint.description), ("Exam clash", "Two exams on one day."))
        self.assertIsNone(complaint.responsible)  # O27: never assigned automatically
        event = complaint.events.get()
        self.assertEqual((event.kind, event.actor), (ComplaintEvent.Kind.SUBMITTED, self.student))

    def test_initial_status_is_received(self):
        self.assertEqual(submit(self.student, self.categories["academic"]).status, Complaint.Status.RECEIVED)

    def test_reference_is_unique_and_readable(self):
        first = submit(self.student, self.categories["academic"])
        second = submit(self.student, self.categories["academic"])
        for complaint in (first, second):
            self.assertRegex(complaint.reference, r"^CMP-\d{4}-\d{5,}$")
        self.assertNotEqual(first.reference, second.reference)

    def test_database_rejects_a_duplicate_reference(self):
        first = submit(self.student, self.categories["academic"])
        second = submit(self.student, self.categories["academic"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Complaint.objects.filter(pk=second.pk).update(reference=first.reference)

    def test_required_fields(self):
        for field in ("title", "description"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as caught:
                    submit(self.student, self.categories["academic"], **{field: "   "})
                self.assertIn(field, caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            submit(self.student, None)
        self.assertIn("category", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            submit(self.student, self.categories["academic"], description="x" * 5001)
        self.assertFalse(Complaint.objects.exists())

    def test_inactive_category_or_subcategory_is_rejected(self):
        category = self.categories["academic"]
        ComplaintSubcategory.objects.filter(pk=self.categories["exams"].pk).update(is_active=False)
        with self.assertRaises(ValidationError) as caught:
            submit(self.student, category, subcategory=self.categories["exams"])
        self.assertIn("subcategory", caught.exception.message_dict)

        ComplaintCategory.objects.filter(pk=category.pk).update(is_active=False)
        category.refresh_from_db()
        with self.assertRaises(ValidationError) as caught:
            submit(self.student, category)
        self.assertIn("category", caught.exception.message_dict)
        self.assertFalse(Complaint.objects.exists())

    def test_subcategory_must_belong_to_the_category(self):
        with self.assertRaises(ValidationError) as caught:
            submit(self.student, self.categories["other"], subcategory=self.categories["exams"])
        self.assertIn("subcategory", caught.exception.message_dict)

    def test_cohort_comes_from_the_students_own_profile(self):
        # The service accepts no cohort input at all; extra arguments are refused.
        with self.assertRaises(TypeError):
            submit(self.student, self.categories["academic"], batch=self.academics["other_batch"])
        self.assertEqual(submit(self.student, self.categories["academic"]).cohort, cohort(self.academics))

    def test_only_active_registered_students_can_submit(self):
        category = self.categories["academic"]
        for user in (make_advisor(cohorts=[cohort(self.academics)]), make_super_admin(), make_student(OTHER_STUDENT_EMAIL)):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                submit(user, category)
        self.student.is_active = False
        self.student.save()
        with self.assertRaises(PermissionDenied):
            submit(self.student, category)

    def test_students_in_a_deactivated_cohort_cannot_submit(self):
        self.academics["section"].is_active = False
        self.academics["section"].save()
        with self.assertRaises(ValidationError):
            submit(self.student, self.categories["academic"])

    def test_duplicates_are_allowed_and_can_be_flagged(self):
        category = self.categories["academic"]
        first = submit(self.student, category)
        second = submit(self.student, category, title=first.title, description=first.description)
        self.assertNotEqual(first.pk, second.pk)  # DEC-225: never blocked
        self.assertEqual(list(services.possible_duplicates(self.student, category)), [second, first])
        services.change_status(make_super_admin(), first, Complaint.Status.REJECTED, "Duplicate of a newer complaint.")
        self.assertEqual(list(services.possible_duplicates(self.student, category)), [second])
        other = make_student(OTHER_STUDENT_EMAIL, academics=self.academics)
        self.assertFalse(services.possible_duplicates(other, category).exists())


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentSubmissionTests(TransactionTestCase):
    """Real concurrent submissions on separate database connections (MySQL)."""

    def test_concurrent_submissions_get_distinct_references(self):
        academics = make_academics()
        category = ComplaintCategory.objects.create(name="Concurrency", position=99)
        students = [make_student(f"1000000{i}@student.uol.edu.pk", academics=academics) for i in range(8)]
        references, errors, barrier = [], [], threading.Barrier(len(students))

        def worker(student):
            try:
                barrier.wait()
                references.append(submit(student, category).reference)
            except Exception as error:  # pragma: no cover - reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(s,)) for s in students]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(set(references)), len(students))
        self.assertTrue(all(re.fullmatch(r"CMP-\d{4}-\d{5,}", r) for r in references))
