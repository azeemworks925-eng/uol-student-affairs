"""
Complaint records and history cannot be changed or deleted through Django's ordinary ORM
paths, including the bulk QuerySet operations that skip Model.save() and Model.delete().
Each test runs the real operation and checks that the database is unchanged afterwards.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from complaints import services
from complaints.models import Complaint, ComplaintEvent, ProtectedRecordError

from .helpers import cohort, make_academics, make_advisor, make_categories, make_student, make_super_admin, submit

Status = Complaint.Status
Kind = ComplaintEvent.Kind


def snapshot(queryset, *fields):
    return list(queryset.order_by("pk").values_list("pk", *fields))


class ImmutabilityTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.categories = make_categories()
        cls.student = make_student(academics=cls.academics)
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)])

    def setUp(self):
        self.complaint = submit(self.student, self.categories["academic"])
        services.respond(self.advisor, self.complaint, "We are looking into it.")
        self.events = ComplaintEvent.objects.filter(complaint=self.complaint)
        self.events_before = snapshot(self.events, "kind", "message", "actor_id")
        self.complaint_before = snapshot(Complaint.objects.all(), "status", "description", "reference")

    def assert_refused(self, operation):
        with self.assertRaises(ProtectedRecordError), transaction.atomic():
            operation()
        self.assertEqual(snapshot(self.events, "kind", "message", "actor_id"), self.events_before)
        self.assertEqual(snapshot(Complaint.objects.all(), "status", "description", "reference"), self.complaint_before)


class EventHistoryTests(ImmutabilityTestCase):
    def test_queryset_update_is_refused(self):
        self.assert_refused(lambda: ComplaintEvent.objects.filter(pk=self.events[0].pk).update(message="edited"))
        self.assert_refused(lambda: ComplaintEvent.objects.update(message="edited"))

    def test_related_manager_update_is_refused(self):
        self.assert_refused(lambda: self.complaint.events.update(message="edited"))

    def test_bulk_update_is_refused(self):
        event = self.events.last()
        event.message = "edited"
        self.assert_refused(lambda: ComplaintEvent.objects.bulk_update([event], ["message"]))

    def test_queryset_delete_is_refused(self):
        self.assert_refused(lambda: ComplaintEvent.objects.filter(complaint=self.complaint).delete())
        self.assert_refused(lambda: ComplaintEvent.objects.all().delete())
        self.assert_refused(lambda: self.complaint.events.all().delete())

    def test_upserting_bulk_create_is_refused(self):
        existing = self.events.first()
        overwrite = ComplaintEvent(
            pk=existing.pk, complaint=self.complaint, actor=self.advisor, kind=Kind.RESPONSE, message="forged"
        )
        self.assert_refused(lambda: ComplaintEvent.objects.bulk_create(
            [overwrite], update_conflicts=True, unique_fields=["id"], update_fields=["kind", "message", "actor"]
        ))

    def test_instance_save_is_refused(self):
        event = self.events.last()
        event.message = "edited"
        self.assert_refused(event.save)

    def test_instance_delete_is_refused(self):
        self.assert_refused(self.events.last().delete)

    def test_refusals_are_validation_errors_for_existing_callers(self):
        self.assertTrue(issubclass(ProtectedRecordError, ValidationError))

    def test_plain_bulk_create_still_inserts_new_events(self):
        # Inserting new history is not a modification; database checks still apply.
        ComplaintEvent.objects.bulk_create([ComplaintEvent(
            complaint=self.complaint, actor=self.student, kind=Kind.FURTHER_INFORMATION, message="Added later."
        )])
        self.assertEqual(self.events.count(), len(self.events_before) + 1)


class ComplaintRecordTests(ImmutabilityTestCase):
    def test_bulk_delete_is_refused(self):
        self.assert_refused(lambda: Complaint.objects.filter(pk=self.complaint.pk).delete())
        self.assert_refused(lambda: Complaint.objects.all().delete())

    def test_bulk_delete_is_refused_even_without_history(self):
        # Previously only the PROTECT link from events stopped this; a complaint with no
        # events (for example, mid-submission) could be bulk-deleted.
        bare = Complaint.objects.create(
            student=self.student, batch=self.academics["batch"], semester=self.academics["semester"],
            section=self.academics["section"], category=self.categories["academic"], title="t", description="d",
        )
        with self.assertRaises(ProtectedRecordError), transaction.atomic():
            Complaint.objects.filter(pk=bare.pk).delete()
        self.assertTrue(Complaint.objects.filter(pk=bare.pk).exists())

    def test_instance_delete_is_refused(self):
        self.assert_refused(self.complaint.delete)

    def test_bulk_updates_are_refused(self):
        self.assert_refused(lambda: Complaint.objects.filter(pk=self.complaint.pk).update(status=Status.RESOLVED))
        self.assert_refused(lambda: Complaint.objects.filter(pk=self.complaint.pk).update(description="replaced"))
        self.complaint.status = Status.RESOLVED
        self.assert_refused(lambda: Complaint.objects.bulk_update([self.complaint], ["status"]))

    def test_original_description_cannot_be_changed_through_save(self):
        complaint = Complaint.objects.get(pk=self.complaint.pk)
        complaint.description = "replaced"
        self.assert_refused(complaint.save)


class LegitimateWorkflowTests(ImmutabilityTestCase):
    """The protections must not get in the way of the complaint services."""

    def test_submission_creates_the_initial_event(self):
        complaint = submit(self.student, self.categories["academic"])
        self.assertRegex(complaint.reference, r"^CMP-\d{4}-\d{5,}$")
        self.assertEqual(list(complaint.events.values_list("kind", flat=True)), [Kind.SUBMITTED])

    def test_status_changes_responses_and_owner_changes_still_work(self):
        admin = make_super_admin()
        updated_before = Complaint.objects.get(pk=self.complaint.pk).updated_at
        services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        services.respond(self.advisor, self.complaint, "Update from the timetable office.")
        services.assign_responsible(admin, self.complaint, self.advisor)
        services.change_status(self.advisor, self.complaint, Status.RESOLVED, "Clash removed.")
        services.mark_still_not_resolved(self.student, self.complaint, "Still clashing.")
        services.add_further_information(self.student, self.complaint, "Tuesday labs.")
        services.request_cancellation(self.student, self.complaint)

        complaint = Complaint.objects.get(pk=self.complaint.pk)
        self.assertEqual((complaint.status, complaint.responsible), (Status.UNDER_REVIEW, self.advisor))
        self.assertGreaterEqual(complaint.updated_at, updated_before)
        self.assertEqual(list(complaint.events.values_list("kind", flat=True)), [
            Kind.SUBMITTED, Kind.RESPONSE, Kind.STATUS_CHANGED, Kind.RESPONSE, Kind.RESPONSIBLE_CHANGED,
            Kind.STATUS_CHANGED, Kind.STILL_NOT_RESOLVED, Kind.FURTHER_INFORMATION, Kind.CANCELLATION_REQUESTED,
        ])
