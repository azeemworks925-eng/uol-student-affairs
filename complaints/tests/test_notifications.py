"""Complaint notification producers (Complaints Part 4 Stage 3; spec section 5.2)."""

import threading
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from complaints import services
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent
from notifications.models import Notification

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


class ProducerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.categories = make_categories()
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=cls.academics, full_name="Zara Ahmed")
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)], full_name="Dr. Ayesha Rahman")
        cls.co_advisor = make_advisor("coadvisor@uol.edu.pk", cohorts=[cohort(cls.academics)], full_name="Mr. Bilal Shah")
        cls.admin = make_super_admin()
        cls.admin.full_name = "Head of Batch Advisors"
        cls.admin.save()

    def setUp(self):
        self.complaint = submit(self.student, self.categories["academic"], title="Lab timetable clash")

    def notifications(self):
        return Notification.objects.filter(target_arg=self.complaint.reference)


class StatusNotificationTests(ProducerTestCase):
    def test_each_staff_status_change_notifies_the_student_once(self):
        services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        services.change_status(self.admin, self.complaint, Status.RESOLVED, "The OS lab moved to Thursday.")
        notifications = list(self.notifications().order_by("created_at", "id"))
        self.assertEqual(len(notifications), 2)
        events = list(self.complaint.events.filter(kind=Kind.STATUS_CHANGED).order_by("created_at", "id"))
        for notification, event, status in zip(notifications, events, ("Under Review", "Resolved")):
            with self.subTest(status=status):
                self.assertEqual(notification.recipient, self.student)
                self.assertEqual(notification.event_type, "complaint.status_changed")
                self.assertEqual((notification.source_type, notification.source_id), ("complaints.complaintevent", event.pk))
                self.assertEqual(notification.title, f"{self.complaint.reference} is now {status}")
                self.assertEqual(notification.body, "Lab timetable clash")
                self.assertEqual((notification.target_url_name, notification.target_arg),
                                 ("student_complaint_detail", self.complaint.reference))
                self.assertIsNone(notification.read_at)

    def test_rejection_reason_and_resolution_note_are_never_in_the_preview(self):
        services.change_status(self.advisor, self.complaint, Status.REJECTED, "Confidential reason about staffing.")
        other = submit(self.student, self.categories["academic"], title="Second")
        services.change_status(self.advisor, other, Status.RESOLVED, "Private resolution detail.")
        for notification in Notification.objects.filter(recipient=self.student):
            with self.subTest(title=notification.title):
                self.assertNotIn("Confidential", notification.title + notification.body)
                self.assertNotIn("Private resolution", notification.title + notification.body)
        self.assertEqual(Notification.objects.get(target_arg=self.complaint.reference).title,
                         f"{self.complaint.reference} is now Rejected")

    def test_refused_status_changes_create_nothing(self):
        for new_status, note, expected in ((Status.RESOLVED, "", Status.RECEIVED), (Status.REJECTED, " ", Status.RECEIVED)):
            with self.subTest(new_status=new_status), self.assertRaises(ValidationError):
                services.change_status(self.advisor, self.complaint, new_status, note)
        services.change_status(self.co_advisor, self.complaint, Status.UNDER_REVIEW)
        with self.assertRaises(ValidationError):  # stale page
            services.change_status(self.advisor, self.complaint, Status.REJECTED, "Stale.", expected_status=Status.RECEIVED)
        self.assertEqual(self.notifications().count(), 1)  # only the co-advisor's real change


class ResponseNotificationTests(ProducerTestCase):
    def test_response_notifies_the_student_with_a_role_attributed_preview(self):
        event = services.respond(self.advisor, self.complaint, "We are checking with the timetable office.")
        notification = self.notifications().get()
        self.assertEqual(notification.event_type, "complaint.response")
        self.assertEqual(notification.source_id, event.pk)
        self.assertEqual(notification.title, f"New response on {self.complaint.reference}")
        self.assertEqual(notification.body, "Batch Advisor: We are checking with the timetable office.")
        services.respond(self.admin, self.complaint, "Escalated.")
        self.assertEqual(self.notifications().order_by("-id").first().body, "Super Admin: Escalated.")

    def test_long_responses_are_truncated_and_the_full_text_stays_on_the_complaint(self):
        message = "word " * 200
        event = services.respond(self.advisor, self.complaint, message)
        body = self.notifications().get().body
        self.assertLess(len(body), len("Batch Advisor: ") + 150)
        self.assertTrue(body.endswith("…"))
        self.assertEqual(ComplaintEvent.objects.get(pk=event.pk).message, message.strip())

    def test_no_account_identity_is_appended(self):
        services.respond(self.advisor, self.complaint, "Please bring your timetable.")
        services.respond(self.admin, self.complaint, "Noted.")
        for notification in self.notifications():
            text = notification.title + notification.body
            for identity in ("Dr. Ayesha Rahman", self.advisor.email, "Head of Batch Advisors", self.admin.email):
                with self.subTest(identity=identity):
                    self.assertNotIn(identity, text)

    def test_names_written_by_staff_in_the_response_are_kept(self):
        services.respond(self.advisor, self.complaint, "Mr. Bilal Shah from the timetable office will call you.")
        body = self.notifications().get().body
        self.assertEqual(body, "Batch Advisor: Mr. Bilal Shah from the timetable office will call you.")


class ExclusionTests(ProducerTestCase):
    def test_other_complaint_events_notify_nobody(self):
        services.add_further_information(self.student, self.complaint, "More detail.")
        services.request_cancellation(self.student, self.complaint, "Sorted.")
        services.assign_responsible(self.admin, self.complaint, self.advisor)
        services.change_status(self.advisor, self.complaint, Status.RESOLVED, "Done.")
        before = Notification.objects.count()
        services.mark_still_not_resolved(self.student, self.complaint, "Still clashing.")
        self.assertEqual(Notification.objects.count(), before)
        kinds = set(Notification.objects.values_list("event_type", flat=True))
        self.assertEqual(kinds, {"complaint.status_changed"})
        # Submission notified nobody either.
        self.assertFalse(Notification.objects.filter(source_id=self.complaint.events.get(kind=Kind.SUBMITTED).pk).exists())

    def test_only_the_submitting_student_is_ever_a_recipient(self):
        services.respond(self.advisor, self.complaint, "Hello.")
        services.change_status(self.co_advisor, self.complaint, Status.UNDER_REVIEW)
        services.respond(self.admin, self.complaint, "Following up.")
        self.assertEqual(set(Notification.objects.values_list("recipient", flat=True)), {self.student.pk})
        for user in (self.advisor, self.co_advisor, self.admin, self.classmate):
            self.assertFalse(Notification.objects.filter(recipient=user).exists())

    def test_the_actor_is_never_notified(self):
        from complaints.notifications import notify_student

        # A defensive guard: a status event whose actor is the student produces nothing.
        event = ComplaintEvent.objects.create(complaint=self.complaint, actor=self.student, kind=Kind.STATUS_CHANGED,
                                              from_status=Status.RECEIVED, to_status=Status.UNDER_REVIEW)
        self.assertIsNone(notify_student(event))
        self.assertFalse(Notification.objects.filter(source_id=event.pk).exists())

    def test_producer_is_idempotent_for_one_event(self):
        from complaints.notifications import notify_student

        event = services.respond(self.advisor, self.complaint, "Once.")
        notify_student(event)
        notify_student(event)
        self.assertEqual(Notification.objects.filter(source_id=event.pk).count(), 1)


class TransactionTests(ProducerTestCase):
    def test_rolled_back_actions_leave_no_notification(self):
        for action in (
            lambda: services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW),
            lambda: services.respond(self.advisor, self.complaint, "Will roll back."),
        ):
            with self.subTest(action=action), self.assertRaises(RuntimeError):
                with transaction.atomic():
                    action()
                    raise RuntimeError("abort after the action")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.RECEIVED)
        self.assertEqual(self.complaint.events.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_a_failed_notification_rolls_the_action_back(self):
        with mock.patch("complaints.notifications.notify", side_effect=IntegrityError("notification failed")):
            with self.assertRaises(IntegrityError):
                services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
            with self.assertRaises(IntegrityError):
                services.respond(self.advisor, self.complaint, "Never saved.")
        self.complaint.refresh_from_db()
        self.assertEqual((self.complaint.status, self.complaint.events.count()), (Status.RECEIVED, 1))
        self.assertEqual(Notification.objects.count(), 0)

    def test_the_view_flow_creates_the_notification(self):
        self.client.force_login(self.advisor)
        self.client.post(reverse("advisor_complaint_respond", args=[self.complaint.reference]), {"message": "Via the workspace."})
        self.client.post(reverse("advisor_complaint_status", args=[self.complaint.reference]),
                         {"new_status": Status.UNDER_REVIEW, "note": "", "expected_status": Status.RECEIVED})
        self.assertEqual(sorted(self.notifications().values_list("event_type", flat=True)),
                         ["complaint.response", "complaint.status_changed"])


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentStatusNotificationTests(TransactionTestCase):
    """Two advisors act on the same stale page at once: one change, one notification (MySQL)."""

    def test_only_one_notification_for_the_successful_change(self):
        a = make_academics()
        category = ComplaintCategory.objects.create(name="Race notifications", position=70)
        student = make_student(academics=a)
        complaint = submit(student, category)
        advisors = [make_advisor(f"racer{i}@uol.edu.pk", cohorts=[cohort(a)]) for i in range(2)]
        targets = [(Status.UNDER_REVIEW, ""), (Status.REJECTED, "Not ours.")]
        results, barrier = [], threading.Barrier(2)

        def worker(advisor, new_status, note):
            try:
                barrier.wait()
                services.change_status(advisor, complaint, new_status, note, expected_status=Status.RECEIVED)
                results.append("ok")
            except ValidationError as error:
                results.append(error.code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(adv, *t)) for adv, t in zip(advisors, targets)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(results, ["ok", "stale_status"])
        self.assertEqual(Notification.objects.filter(recipient=student).count(), 1)
        event = complaint.events.get(kind=Kind.STATUS_CHANGED)
        self.assertEqual(Notification.objects.get(recipient=student).source_id, event.pk)
