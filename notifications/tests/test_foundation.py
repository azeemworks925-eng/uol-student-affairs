"""Notification foundation: model protection, registry and source checks, user-facing services."""

import threading

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from accounts.tests.helpers import make_academics, make_advisor, make_student, make_super_admin
from complaints.models import ComplaintCategory, ComplaintEvent
from complaints.tests.helpers import submit
from notifications import registry, services
from notifications.models import Notification, ProtectedNotificationError

OTHER = "87654321@student.uol.edu.pk"


class FoundationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_student(academics=make_academics())
        cls.other_student = make_student(OTHER)
        category = ComplaintCategory.objects.create(name="Foundation", position=50)
        cls.complaint = submit(cls.student, category)
        cls.event = cls.complaint.events.get()  # a saved ComplaintEvent to act as the source

    def make(self, recipient=None, source=None, **overrides):
        data = {
            "event_type": "complaint.response",
            "source": source or self.event,
            "title": "Title",
            "body": "Body",
            "target_url_name": "student_complaint_detail",
            "target_arg": self.complaint.reference,
        }
        data.update(overrides)
        return services.notify(recipient or self.student, **data)


class ModelProtectionTests(FoundationTestCase):
    """Only read_at may change on an existing notification; inserts stay possible."""

    def setUp(self):
        self.notification, _ = self.make()

    def stored(self):
        return Notification.objects.filter(pk=self.notification.pk).values_list("title", "body", "event_type", "recipient_id", "read_at").get()

    def assert_refused(self, operation):
        before = self.stored()
        with self.assertRaises(ProtectedNotificationError), transaction.atomic():
            operation()
        self.assertEqual(self.stored(), before)

    def test_queryset_update_of_content_is_refused(self):
        qs = Notification.objects.filter(pk=self.notification.pk)
        self.assert_refused(lambda: qs.update(title="Edited"))
        self.assert_refused(lambda: qs.update(recipient=self.other_student))
        self.assert_refused(lambda: qs.update(read_at=timezone.now(), body="Edited"))

    def test_bulk_update_of_content_is_refused(self):
        self.notification.title = "Edited"
        self.assert_refused(lambda: Notification.objects.bulk_update([self.notification], ["title"]))
        self.assert_refused(lambda: Notification.objects.bulk_update([self.notification], ["read_at", "target_url_name"]))

    def test_upserting_bulk_create_is_refused(self):
        overwrite = Notification(pk=self.notification.pk, recipient=self.student, event_type="complaint.response",
                                 source_type="complaints.complaintevent", source_id=self.event.pk, title="Forged",
                                 target_url_name="student_complaint_detail")
        self.assert_refused(lambda: Notification.objects.bulk_create(
            [overwrite], update_conflicts=True, unique_fields=["id"], update_fields=["title"]))
        self.assert_refused(lambda: Notification.objects.bulk_create(
            [overwrite], update_conflicts=True, unique_fields=["id"], update_fields=["read_at"]))

    def test_instance_saves_that_change_content_are_refused(self):
        loaded = Notification.objects.get(pk=self.notification.pk)
        loaded.title = "Edited"
        self.assert_refused(loaded.save)
        self.assert_refused(lambda: loaded.save(update_fields=["title"]))
        self.assert_refused(lambda: loaded.save(update_fields=["title", "read_at"]))
        forged = Notification(pk=self.notification.pk, recipient=self.student, event_type="complaint.response",
                              source_type="complaints.complaintevent", source_id=self.event.pk, title="Forged",
                              target_url_name="student_complaint_detail", created_at=timezone.now())
        self.assert_refused(forged.save)

    def test_read_state_can_change(self):
        now = timezone.now()
        self.assertEqual(Notification.objects.filter(pk=self.notification.pk).update(read_at=now), 1)
        loaded = Notification.objects.get(pk=self.notification.pk)
        loaded.read_at = None
        loaded.save(update_fields=["read_at"])
        loaded.read_at = now
        self.assertEqual(Notification.objects.bulk_update([loaded], ["read_at"]), 1)
        self.assertIsNotNone(Notification.objects.get(pk=self.notification.pk).read_at)

    def test_ordinary_inserts_still_work(self):
        other_event = ComplaintEvent.objects.create(complaint=self.complaint, actor=self.student, kind="further_information", message="x")
        Notification.objects.bulk_create([Notification(
            recipient=self.other_student, event_type="complaint.response", source_type="complaints.complaintevent",
            source_id=other_event.pk, title="Inserted", target_url_name="student_complaint_detail")])
        Notification(recipient=self.student, event_type="complaint.response", source_type="complaints.complaintevent",
                     source_id=other_event.pk, title="Saved", target_url_name="student_complaint_detail").save()
        self.assertEqual(Notification.objects.filter(source_id=other_event.pk).count(), 2)

    def test_database_allows_one_notification_per_recipient_and_source(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(recipient=self.student, event_type="complaint.response", source_type="complaints.complaintevent",
                                        source_id=self.event.pk, title="Duplicate", target_url_name="student_complaint_detail")
        # A different recipient for the same source is a different notification.
        Notification.objects.create(recipient=self.other_student, event_type="complaint.response", source_type="complaints.complaintevent",
                                    source_id=self.event.pk, title="Other", target_url_name="student_complaint_detail")


class NotifyValidationTests(FoundationTestCase):
    def test_valid_notification(self):
        notification, created = self.make(title="t" * 200, body="b" * 400)
        self.assertTrue(created)
        self.assertEqual((notification.recipient, notification.source_type, notification.source_id),
                         (self.student, "complaints.complaintevent", self.event.pk))
        self.assertLessEqual(len(notification.title), 150)
        self.assertLessEqual(len(notification.body), 300)
        self.assertIsNone(notification.read_at)

    def test_repeat_for_the_same_source_returns_the_existing_row(self):
        first, created = self.make()
        second, created_again = self.make(title="Different")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().title, "Title")

    def test_unregistered_type_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(event_type="complaint.submitted")

    def test_source_must_be_the_declared_model(self):
        with self.assertRaises(ValidationError):
            self.make(source=self.complaint)  # a Complaint, not a ComplaintEvent
        with self.assertRaises(ValidationError):
            self.make(source=self.student)

    def test_source_must_be_saved(self):
        with self.assertRaises(ValidationError):
            self.make(source=ComplaintEvent(complaint=self.complaint, actor=self.student, kind="response", message="x"))

    def test_destination_must_be_allowed_and_resolvable(self):
        for url_name, arg in (("super_admin_complaint_detail", self.complaint.reference), ("student_complaints", "")):
            with self.subTest(url_name=url_name), self.assertRaises(ValidationError):
                self.make(target_url_name=url_name, target_arg=arg)
        self.assertEqual(Notification.objects.count(), 0)

    def test_registry_declares_source_model_and_destinations(self):
        for key, notification_type in registry.REGISTRY.items():
            with self.subTest(type=key):
                self.assertEqual(notification_type.source_model, "complaints.complaintevent")
                self.assertEqual(notification_type.destinations, {"student_complaint_detail"})

    def test_inactive_recipients_still_receive_and_keep_notifications(self):
        self.student.is_active = False
        self.student.save()
        notification, created = self.make()
        self.assertTrue(created)
        self.assertEqual(services.unread_count(self.student), 0)  # cannot see them while inactive
        self.student.is_active = True
        self.student.save()
        self.assertEqual(list(services.for_user(self.student)), [notification])
        self.assertEqual(services.unread_count(self.student), 1)


class UserFacingServiceTests(FoundationTestCase):
    def setUp(self):
        self.mine, _ = self.make()
        second_event = ComplaintEvent.objects.create(complaint=self.complaint, actor=self.student, kind="further_information", message="x")
        self.other, _ = self.make(recipient=self.other_student, source=second_event)

    def test_counts_and_lists_are_scoped_to_the_user(self):
        self.assertEqual(list(services.for_user(self.student)), [self.mine])
        self.assertEqual(services.unread_count(self.student), 1)
        self.assertEqual(services.unread_count(self.other_student), 1)

    def test_inactive_and_anonymous_users_get_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.student.is_active = False
        for user in (AnonymousUser(), self.student, None):
            with self.subTest(user=user):
                self.assertEqual(list(services.for_user(user)), [])
                self.assertEqual(services.unread_count(user), 0)
                self.assertIsNone(services.mark_read(user, self.mine.pk))
                self.assertEqual(services.mark_all_read(user), 0)
        self.mine.refresh_from_db()
        self.assertIsNone(self.mine.read_at)

    def test_mark_read_is_idempotent_and_scoped(self):
        self.assertIsNone(services.mark_read(self.student, self.other.pk))  # not theirs
        self.other.refresh_from_db()
        self.assertIsNone(self.other.read_at)
        first = services.mark_read(self.student, self.mine.pk).read_at
        self.assertIsNotNone(first)
        self.assertEqual(services.mark_read(self.student, self.mine.pk).read_at, first)  # first read time kept

    def test_mark_all_read_only_touches_own_notifications(self):
        self.assertEqual(services.mark_all_read(self.student), 1)
        self.other.refresh_from_db()
        self.assertIsNone(self.other.read_at)
        self.assertEqual(services.unread_count(self.student), 0)

    def test_destination_is_built_from_the_registry_only(self):
        self.assertEqual(services.destination_url(self.mine), reverse("student_complaint_detail", args=[self.complaint.reference]))
        # A tampered row (as if edited directly in the database) never yields an arbitrary target.
        Notification.objects.filter(pk=self.mine.pk).update(read_at=None)
        for url_name, arg in (("admin:index", ""), ("student_complaint_detail", "a/../../x"), ("https://evil.example", "")):
            tampered = Notification(event_type="complaint.response", target_url_name=url_name, target_arg=arg)
            with self.subTest(url_name=url_name):
                result = services.destination_url(tampered)
                self.assertTrue(result is None or result.startswith("/student/complaints/"))
        unknown_type = Notification(event_type="unknown", target_url_name="student_complaint_detail", target_arg="CMP-1")
        self.assertIsNone(services.destination_url(unknown_type))


class MigrationTests(TransactionTestCase):
    """The single migration is reversible on MySQL and SQLite."""

    def test_migration_can_be_reversed_and_reapplied(self):
        executor = MigrationExecutor(connection)
        table = Notification._meta.db_table
        executor.migrate([("notifications", None)])
        with connection.cursor() as cursor:
            self.assertNotIn(table, connection.introspection.table_names(cursor))
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            self.assertIn(table, connection.introspection.table_names(cursor))
            constraints = connection.introspection.get_constraints(cursor, table)
        self.assertIn("unique_notification_per_recipient_source", constraints)
        self.assertIn("notification_unread_idx", constraints)
        self.assertIn("notification_recent_idx", constraints)


@skipUnlessDBFeature("has_select_for_update")
class ConcurrencyTests(TransactionTestCase):
    """Real concurrent writers on separate MySQL connections."""

    def run_threads(self, targets):
        barrier, errors = threading.Barrier(len(targets)), []

        def wrap(target):
            try:
                barrier.wait()
                target()
            except Exception as error:  # pragma: no cover - reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=wrap, args=(t,)) for t in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def setUp(self):
        self.student = make_student(academics=make_academics())
        category = ComplaintCategory.objects.create(name="Concurrency notifications", position=60)
        self.complaint = submit(self.student, category)
        self.event = self.complaint.events.get()

    def test_concurrent_notify_for_one_source_creates_one_row(self):
        def produce():
            with transaction.atomic():
                services.notify(self.student, event_type="complaint.response", source=self.event, title="T",
                                target_url_name="student_complaint_detail", target_arg=self.complaint.reference)

        self.run_threads([produce] * 4)
        self.assertEqual(Notification.objects.filter(source_id=self.event.pk).count(), 1)

    def test_concurrent_mark_read_keeps_one_timestamp(self):
        notification, _ = services.notify(self.student, event_type="complaint.response", source=self.event, title="T",
                                          target_url_name="student_complaint_detail", target_arg=self.complaint.reference)
        self.run_threads([lambda: services.mark_read(self.student, notification.pk)] * 4)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
