"""`manage.py seed_demo`: DEBUG only, safe to run twice, real history through the services."""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import AcademicTerm, Batch, Section, Semester
from accounts.models import AdvisorAssignment, StudentProfile, User
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent
from notifications.models import Notification
from meetings.models import Meeting, MeetingEvent
from voice.models import Submission


def snapshot():
    return [model.objects.count() for model in (
        User, StudentProfile, AdvisorAssignment, Batch, Section, AcademicTerm, ComplaintCategory,
        Complaint, ComplaintEvent, Notification, Submission, Meeting, MeetingEvent)]


@override_settings(DEMO_STAFF_EMAILS=[])  # independent of the laptop's .env
class SeedDemoTests(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        return out.getvalue()

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaisesMessage(CommandError, "DEBUG"):
            self.run_seed()
        self.assertEqual(Complaint.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_creates_demo_data_and_is_safe_to_run_twice(self):
        first = self.run_seed()
        self.assertIn("Demo data ready", first)
        counts = snapshot()
        self.assertIn("Demo data already present", self.run_seed())
        self.assertEqual(snapshot(), counts)

        batch = Batch.objects.get(name="DEMO — Fall 2026")
        for name in ("DEMO-A", "DEMO-B"):
            self.assertEqual(StudentProfile.objects.filter(batch=batch, section__name=name, semester__number=4).count(), 6)
        self.assertTrue(AcademicTerm.objects.filter(is_current=True).exists())
        self.assertEqual(User.objects.filter(role=User.Role.BATCH_ADVISOR).count(), 2)
        self.assertEqual(AdvisorAssignment.objects.filter(batch=batch).count(), 3)
        self.assertTrue(User.objects.get(email="demo.admin@uol.edu.pk").is_super_admin)

        complaints = Complaint.objects.all()
        self.assertEqual(complaints.count(), 15)
        self.assertEqual(set(complaints.values_list("status", flat=True)), set(Complaint.Status.values))
        self.assertEqual(complaints.values("category").distinct().count(), 4)
        # Real history and notifications, from the services.
        self.assertEqual(ComplaintEvent.objects.filter(kind=ComplaintEvent.Kind.SUBMITTED).count(), 15)
        status_events = ComplaintEvent.objects.filter(kind__in=[ComplaintEvent.Kind.STATUS_CHANGED, ComplaintEvent.Kind.RESPONSE])
        self.assertEqual(Notification.objects.filter(source_type="complaints.complaintevent").count(), status_events.count())
        self.assertFalse(complaints.filter(reference__isnull=True).exists())
        # Student Voice: all types and statuses, in both cohorts, with one notification per answer.
        voice = Submission.objects.all()
        self.assertEqual(voice.count(), 8)
        self.assertEqual(set(voice.values_list("type", flat=True)), set(Submission.Type.values))
        self.assertEqual(set(voice.values_list("status", flat=True)), set(Submission.Status.values))
        self.assertEqual(set(voice.values_list("section__name", flat=True)), {"DEMO-A", "DEMO-B"})
        self.assertEqual(Notification.objects.filter(source_type="voice.submission").count(),
                         voice.exclude(answer="").count())
        # Submission times are spread over the past three weeks, all in the past.
        oldest, newest = complaints.order_by("created_at").first(), complaints.order_by("created_at").last()
        self.assertGreaterEqual((newest.created_at - oldest.created_at).days, 10)
        self.assertLess(newest.created_at, timezone.now())
        # The demo student has updates, some already read and two still new.
        demo = User.objects.get(email="12345678@student.uol.edu.pk")
        self.assertEqual(Notification.objects.filter(recipient=demo, read_at__isnull=True).count(), 2)
        self.assertGreater(Notification.objects.filter(recipient=demo, read_at__isnull=False).count(), 0)

    @override_settings(DEBUG=True)
    def test_keeps_existing_demo_records(self):
        batch = Batch.objects.create(name="DEMO ? Fall 2026")  # saved earlier without the em dash
        semester = Semester.objects.create(number=4)
        section = Section.objects.create(name="DEMO-A")
        student = User.objects.create_user(email="12345678@student.uol.edu.pk", full_name="Existing Name")
        StudentProfile.objects.create(user=student, batch=batch, semester=semester, section=section)
        self.run_seed()
        batch.refresh_from_db()
        self.assertEqual(batch.name, "DEMO — Fall 2026")
        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(User.objects.get(pk=student.pk).full_name, "Existing Name")
        self.assertEqual(Complaint.objects.filter(student=student).count(), 4)
