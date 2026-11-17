from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from complaints import services
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent
from complaints.permissions import visible_complaints

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

Status = Complaint.Status
Kind = ComplaintEvent.Kind


class WorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.categories = make_categories()
        cls.student = make_student(academics=cls.academics)
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=cls.academics)
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)])
        cls.other_advisor = make_advisor("other@uol.edu.pk", cohorts=[cohort(cls.academics, batch="other_batch")])
        cls.admin = make_super_admin()

    def setUp(self):
        self.complaint = submit(self.student, self.categories["academic"])

    def kinds(self):
        return list(self.complaint.events.values_list("kind", flat=True))

    def resolve(self, note="Timetable corrected."):
        return services.change_status(self.advisor, self.complaint, Status.RESOLVED, note)


class StatusTransitionTests(WorkflowTestCase):
    def test_advisor_moves_a_complaint_through_review_to_resolution(self):
        services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        complaint = self.resolve()
        self.assertEqual(complaint.status, Status.RESOLVED)
        event = complaint.events.last()
        self.assertEqual(
            (event.kind, event.actor, event.from_status, event.to_status, event.message),
            (Kind.STATUS_CHANGED, self.advisor, Status.UNDER_REVIEW, Status.RESOLVED, "Timetable corrected."),
        )

    def test_resolution_requires_a_note(self):
        for note in ("", "   "):
            with self.subTest(note=note), self.assertRaises(ValidationError) as caught:
                services.change_status(self.advisor, self.complaint, Status.RESOLVED, note)
            self.assertIn("note", caught.exception.message_dict)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.RECEIVED)

    def test_rejection_requires_a_reason(self):
        with self.assertRaises(ValidationError) as caught:
            services.change_status(self.advisor, self.complaint, Status.REJECTED)
        self.assertIn("note", caught.exception.message_dict)
        complaint = services.change_status(self.advisor, self.complaint, Status.REJECTED, "Outside the department's remit.")
        self.assertEqual(complaint.events.last().message, "Outside the department's remit.")

    def test_database_also_requires_closing_notes(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ComplaintEvent.objects.bulk_create([ComplaintEvent(
                complaint=self.complaint, actor=self.advisor, kind=Kind.STATUS_CHANGED,
                from_status=Status.RECEIVED, to_status=Status.REJECTED, message="",
            )])

    def test_closed_complaints_cannot_be_changed_by_staff(self):
        self.resolve()
        for new_status in (Status.UNDER_REVIEW, Status.REJECTED, Status.RECEIVED):
            with self.subTest(new_status=new_status), self.assertRaises(ValidationError):
                services.change_status(self.advisor, self.complaint, new_status, "note")
        with self.assertRaises(ValidationError):
            services.change_status(self.advisor, self.complaint, "overdue", "note")  # DEC-226

    def test_only_cohort_advisors_and_super_admins_change_status(self):
        for user in (self.student, self.classmate, self.other_advisor):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.change_status(user, self.complaint, Status.UNDER_REVIEW)
        self.assertEqual(services.change_status(self.admin, self.complaint, Status.UNDER_REVIEW).status, Status.UNDER_REVIEW)

    def test_response_never_changes_the_status(self):
        event = services.respond(self.advisor, self.complaint, "We are checking with the timetable office.")
        self.complaint.refresh_from_db()
        self.assertEqual((event.kind, self.complaint.status), (Kind.RESPONSE, Status.RECEIVED))
        with self.assertRaises(ValidationError):
            services.respond(self.advisor, self.complaint, "  ")
        for user in (self.student, self.other_advisor):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.respond(user, self.complaint, "Hello")


class StudentActionTests(WorkflowTestCase):
    def test_still_not_resolved_returns_a_resolved_complaint_to_under_review(self):
        self.resolve()
        complaint = services.mark_still_not_resolved(self.student, self.complaint, "The clash is still there.")
        self.assertEqual(complaint.status, Status.UNDER_REVIEW)
        event = complaint.events.last()
        self.assertEqual(
            (event.kind, event.actor, event.from_status, event.to_status),
            (Kind.STILL_NOT_RESOLVED, self.student, Status.RESOLVED, Status.UNDER_REVIEW),
        )
        # Then the normal workflow continues.
        self.assertEqual(self.resolve("Fixed for good.").status, Status.RESOLVED)

    def test_still_not_resolved_needs_a_resolved_complaint_and_its_owner(self):
        with self.assertRaises(ValidationError):
            services.mark_still_not_resolved(self.student, self.complaint)
        self.resolve()
        for user in (self.classmate, self.advisor, self.admin):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.mark_still_not_resolved(user, self.complaint)

    def test_further_information_preserves_the_original_and_history(self):
        original = self.complaint.description
        services.respond(self.advisor, self.complaint, "Which lab sessions?")
        services.add_further_information(self.student, self.complaint, "Tuesday 9:00, labs 2 and 4.")
        services.add_further_information(self.student, self.complaint, "Also Thursday.")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.description, original)
        self.assertEqual(self.kinds(), [Kind.SUBMITTED, Kind.RESPONSE, Kind.FURTHER_INFORMATION, Kind.FURTHER_INFORMATION])
        self.assertEqual(self.complaint.status, Status.RECEIVED)
        with self.assertRaises(ValidationError):
            services.add_further_information(self.student, self.complaint, "")
        for user in (self.classmate, self.advisor):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.add_further_information(user, self.complaint, "More")

    def test_original_description_cannot_be_overwritten(self):
        self.complaint.refresh_from_db()
        self.complaint.description = "Replaced"
        with self.assertRaises(ValidationError):
            self.complaint.save()

    def test_history_is_immutable(self):
        event = self.complaint.events.get()
        event.message = "edited"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_complaints_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            self.complaint.delete()
        # Even a bulk delete is stopped by the protected history.
        with self.assertRaises(ProtectedError), transaction.atomic():
            Complaint.objects.filter(pk=self.complaint.pk).delete()
        self.assertTrue(Complaint.objects.filter(pk=self.complaint.pk).exists())

    def test_students_cannot_change_status_directly(self):
        for new_status in Status.values:
            with self.subTest(new_status=new_status), self.assertRaises(PermissionDenied):
                services.change_status(self.student, self.complaint, new_status, "note")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.RECEIVED)

    def test_cancellation_request_is_recorded_without_an_invented_outcome(self):
        event = services.request_cancellation(self.student, self.complaint, "Sorted out with the lab staff.")
        self.complaint.refresh_from_db()
        self.assertEqual((event.kind, event.actor, event.message), (Kind.CANCELLATION_REQUESTED, self.student, "Sorted out with the lab staff."))
        # O28 is open: the status is unchanged, nothing is deleted, nobody approves anything.
        self.assertEqual(self.complaint.status, Status.RECEIVED)
        self.assertIn(self.complaint, visible_complaints(self.advisor))
        self.assertEqual(self.kinds(), [Kind.SUBMITTED, Kind.CANCELLATION_REQUESTED])
        for user in (self.classmate, self.advisor, self.admin):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.request_cancellation(user, self.complaint)


class ResponsibleOwnerTests(WorkflowTestCase):
    """DEC-227/228. How the owner is designated by default is OPEN (O27): never automatic."""

    def test_new_complaints_have_no_owner_even_with_one_advisor(self):
        self.assertIsNone(self.complaint.responsible)

    def test_super_admin_assigns_reassigns_and_takes_over(self):
        co_advisor = make_advisor("coadvisor@uol.edu.pk", cohorts=[cohort(self.academics)])
        services.assign_responsible(self.admin, self.complaint, self.advisor)
        services.assign_responsible(self.admin, self.complaint, co_advisor)
        complaint = services.assign_responsible(self.admin, self.complaint, self.admin)
        self.assertEqual(complaint.responsible, self.admin)
        owners = list(complaint.events.filter(kind=Kind.RESPONSIBLE_CHANGED).values_list("responsible", flat=True))
        self.assertEqual(owners, [self.advisor.pk, co_advisor.pk, self.admin.pk])

    def test_owner_must_be_an_advisor_of_the_exact_cohort(self):
        for owner in (self.other_advisor, self.student, None):
            with self.subTest(owner=owner), self.assertRaises(ValidationError):
                services.assign_responsible(self.admin, self.complaint, owner)

    def test_only_the_super_admin_assigns(self):
        for user in (self.advisor, self.student):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.assign_responsible(user, self.complaint, self.advisor)


class HistoryPreservationTests(WorkflowTestCase):
    def test_deactivated_academic_structure_preserves_complaints_and_access(self):
        services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        for key in ("batch", "semester", "section"):
            entry = self.academics[key]
            entry.is_active = False
            entry.save()
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.cohort, cohort(self.academics))
        self.assertEqual(self.kinds(), [Kind.SUBMITTED, Kind.STATUS_CHANGED])
        for user in (self.student, self.advisor, self.admin):
            with self.subTest(user=user.email):
                self.assertIn(self.complaint, visible_complaints(user))
        # The advisor can still work on it; only new submissions need an active cohort.
        self.assertEqual(self.resolve().status, Status.RESOLVED)
        with self.assertRaises(ValidationError):
            submit(self.student, self.categories["academic"])
        # Structure entries with complaints cannot be deleted at all.
        with self.assertRaises(ProtectedError):
            self.academics["section"].delete()

    def test_deactivated_category_keeps_existing_complaints_but_blocks_new_ones(self):
        category = self.categories["academic"]
        ComplaintCategory.objects.filter(pk=category.pk).update(is_active=False)
        category.refresh_from_db()
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.category, category)
        self.assertIn(self.complaint, visible_complaints(self.student))
        with self.assertRaises(ValidationError):
            submit(self.student, category)
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_deactivated_student_keeps_their_complaints_for_staff(self):
        self.student.is_active = False
        self.student.save()
        self.assertIn(self.complaint, visible_complaints(self.advisor))
        self.assertEqual(list(visible_complaints(self.student)), [])
