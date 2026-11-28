"""Meetings: transitions and who may do them, privacy, validation, notifications, Google Calendar
link, month view, overlap warning and Student Home."""

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CohortRepresentation
from accounts.tests.helpers import OTHER_STUDENT_EMAIL, cohort, make_academics, make_advisor, make_student, make_super_admin
from meetings import services
from meetings.models import Meeting, MeetingEvent, ProtectedMeetingError
from meetings.presentation import (build_month, google_calendar_url, group_by_day, local_datetime, overlap_warnings,
                                   parse_month, student_home_updates)
from notifications.models import Notification

Status = Meeting.Status
REASON = "I would like to discuss my course load."


def future(days=3, hour=10, minute=0):
    return local_datetime(timezone.localdate() + timedelta(days=days), time(hour, minute))


def slot(days=3, hour=10, minute=0, duration=30):
    return {"starts_at": future(days, hour, minute), "duration": duration, "location": "Room 204"}


def slot_post(prefix, days=3, hour=10, minute=0, duration=30, **extra):
    day = timezone.localdate() + timedelta(days=days)
    data = {f"{prefix}-date": day.isoformat(), f"{prefix}-time": f"{hour:02d}:{minute:02d}",
            f"{prefix}-duration": str(duration), f"{prefix}-location": "Room 204"}
    data.update(extra)
    return data


class MeetingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.cohort = cohort(cls.academics)
        cls.other_cohort = cohort(cls.academics, section="other_section")
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=cls.academics, full_name="Sara Classmate")
        cls.outsider = make_student("70000009@student.uol.edu.pk", academics=cls.academics, cohort=cls.other_cohort,
                                    full_name="Other Section")
        cls.advisor = make_advisor(cohorts=[cls.cohort], full_name="First Advisor")
        cls.co_advisor = make_advisor("co@uol.edu.pk", cohorts=[cls.cohort], full_name="Second Advisor")
        cls.other_advisor = make_advisor("other@uol.edu.pk", cohorts=[cls.other_cohort], full_name="Other Advisor")
        cls.near_advisor = make_advisor("near@uol.edu.pk", cohorts=[cohort(cls.academics, semester="other_semester")],
                                        full_name="Near Advisor")
        cls.admin = make_super_admin()

    def request(self, student=None, **overrides):
        data = {"reason": REASON, "preferred_at": future()}
        data.update(overrides)
        return services.request_meeting(student or self.student, **data)

    def confirmed(self, **slot_overrides):
        return services.confirm(self.advisor, self.request(), **{**slot(), **slot_overrides})

    def suggested(self):
        return services.suggest(self.advisor, self.request(), **slot(), note="Does this suit you?")

    def notices(self, student=None):
        return Notification.objects.filter(recipient=student or self.student, source_type="meetings.meetingevent")


class TransitionTests(MeetingTestCase):
    def test_request_copies_the_cohort(self):
        meeting = self.request()
        self.assertEqual(meeting.status, Status.REQUESTED)
        self.assertEqual((meeting.batch, meeting.semester, meeting.section), self.cohort)
        self.assertIsNone(meeting.advisor)
        self.assertEqual(meeting.events.get().kind, MeetingEvent.Kind.REQUESTED)

    def test_status_names(self):
        self.assertEqual(Status.labels, ["Requested", "Time suggested", "Confirmed", "Declined", "Cancelled"])

    def test_any_cohort_advisor_confirms_and_becomes_the_advisor(self):
        meeting = services.confirm(self.co_advisor, self.request(), **slot(duration=45))
        self.assertEqual(meeting.status, Status.CONFIRMED)
        self.assertEqual(meeting.advisor, self.co_advisor)
        self.assertEqual(meeting.ends_at, future() + timedelta(minutes=45))

    def test_suggest_then_accept(self):
        meeting = self.suggested()
        self.assertEqual(meeting.status, Status.TIME_SUGGESTED)
        self.assertEqual(meeting.suggestion_note, "Does this suit you?")
        meeting = services.accept_suggestion(self.student, meeting)
        self.assertEqual(meeting.status, Status.CONFIRMED)
        self.assertEqual(meeting.advisor, self.advisor)

    def test_suggest_then_student_declines(self):
        self.assertEqual(services.decline_suggestion(self.student, self.suggested()).status, Status.DECLINED)

    def test_advisor_declines_with_a_required_reason(self):
        meeting = self.request()
        for reason in ("", "   "):
            with self.subTest(reason=reason), self.assertRaises(ValidationError):
                services.decline(self.advisor, meeting, reason)
        meeting = services.decline(self.advisor, meeting, "Please use the complaints page.")
        self.assertEqual((meeting.status, meeting.closed_reason), (Status.DECLINED, "Please use the complaints page."))

    def test_either_side_cancels_a_confirmed_meeting_with_a_reason(self):
        for actor in (self.student, self.advisor, self.co_advisor):
            with self.subTest(actor=actor.email):
                meeting = self.confirmed()
                with self.assertRaises(ValidationError):
                    services.cancel(actor, meeting, " ")
                self.assertEqual(services.cancel(actor, meeting, "Something came up.").status, Status.CANCELLED)

    def test_a_started_meeting_cannot_be_cancelled(self):
        meeting = self.confirmed()
        with mock.patch("django.utils.timezone.now", return_value=meeting.starts_at + timedelta(minutes=1)):
            with self.assertRaises(ValidationError):
                services.cancel(self.student, meeting, "Too late.")

    def test_advisor_schedules_directly_as_confirmed(self):
        meeting = services.schedule(self.advisor, self.student, reason=REASON, **slot())
        self.assertEqual((meeting.status, meeting.advisor), (Status.CONFIRMED, self.advisor))
        self.assertIsNone(meeting.preferred_at)

    def test_schedule_refuses_a_student_of_another_cohort(self):
        with self.assertRaises(PermissionDenied):
            services.schedule(self.advisor, self.outsider, reason=REASON, **slot())

    def test_invalid_transitions_are_refused(self):
        requested, suggested, confirmed = self.request(), self.suggested(), self.confirmed()
        declined = services.decline(self.advisor, self.request(), "No longer needed.")
        cancelled = services.cancel(self.student, self.confirmed(), "Something came up.")
        advisor_actions = [
            lambda m: services.confirm(self.advisor, m, **slot()),
            lambda m: services.suggest(self.advisor, m, **slot()),
            lambda m: services.decline(self.advisor, m, "A reason."),
        ]
        for meeting in (suggested, confirmed, declined, cancelled):
            for action in advisor_actions:
                with self.subTest(status=meeting.status), self.assertRaises(ValidationError):
                    action(meeting)
        for meeting in (requested, confirmed, declined, cancelled):
            for action in (services.accept_suggestion, services.decline_suggestion):
                with self.subTest(status=meeting.status), self.assertRaises(ValidationError):
                    action(self.student, meeting)
        for meeting in (requested, suggested, declined, cancelled):
            with self.subTest(status=meeting.status), self.assertRaises(ValidationError):
                services.cancel(self.advisor, meeting, "A reason.")

    def test_who_may_not_act(self):
        requested, suggested, confirmed = self.request(), self.suggested(), self.confirmed()
        for outsider in (self.other_advisor, self.near_advisor, self.admin, self.classmate):
            with self.subTest(user=outsider.email):
                with self.assertRaises(PermissionDenied):
                    services.confirm(outsider, requested, **slot())
                with self.assertRaises(PermissionDenied):
                    services.suggest(outsider, requested, **slot())
                with self.assertRaises(PermissionDenied):
                    services.decline(outsider, requested, "A reason.")
                with self.assertRaises(PermissionDenied):
                    services.accept_suggestion(outsider, suggested)
                with self.assertRaises(PermissionDenied):
                    services.decline_suggestion(outsider, suggested)
                with self.assertRaises(PermissionDenied):
                    services.cancel(outsider, confirmed, "A reason.")
        with self.assertRaises(PermissionDenied):  # the advisor cannot answer for the student
            services.accept_suggestion(self.advisor, suggested)
        with self.assertRaises(PermissionDenied):  # the student cannot confirm their own request
            services.confirm(self.student, requested, **slot())

    def test_records_are_protected(self):
        meeting = self.request()
        with self.assertRaises(ProtectedMeetingError):
            meeting.delete()
        with self.assertRaises(ProtectedMeetingError):
            Meeting.objects.all().delete()
        with self.assertRaises(ProtectedMeetingError):
            Meeting.objects.update(status=Status.CONFIRMED)
        meeting.reason = "A changed reason for the meeting."
        with self.assertRaises(ProtectedMeetingError):
            meeting.save()
        event = MeetingEvent.objects.get(meeting_id=meeting.pk)
        event.note = "changed"
        with self.assertRaises(ProtectedMeetingError):
            event.save()

    def test_a_final_status_cannot_be_reopened(self):
        meeting = services.decline(self.advisor, self.request(), "Not needed.")
        meeting.status = Status.REQUESTED
        with self.assertRaises(ProtectedMeetingError):
            meeting.save()


class ValidationTests(MeetingTestCase):
    def test_reason_length(self):
        for reason in ("", "too short", " " * 5 + "123456789" + " " * 5, "x" * 501):
            with self.subTest(length=len(reason)), self.assertRaises(ValidationError):
                self.request(reason=reason)
        self.assertEqual(len(self.request(reason="x" * 10).reason), 10)
        self.assertEqual(len(self.request(reason="x" * 500).reason), 500)

    def test_past_times_are_refused_everywhere(self):
        past = timezone.now() - timedelta(minutes=1)
        with self.assertRaises(ValidationError):
            self.request(preferred_at=past)
        meeting = self.request()
        bad = {"starts_at": past, "duration": 30, "location": "Room 204"}
        for action in (lambda: services.confirm(self.advisor, meeting, **bad),
                       lambda: services.suggest(self.advisor, meeting, **bad),
                       lambda: services.schedule(self.advisor, self.student, reason=REASON, **bad)):
            with self.assertRaises(ValidationError):
                action()

    def test_student_form_refuses_a_past_date(self):
        self.client.force_login(self.student)
        yesterday = timezone.localdate() - timedelta(days=1)
        response = self.client.post(reverse("student_meetings"), {"reason": REASON, "date": yesterday.isoformat(), "time": "10:00"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose a date and time in the future.", status_code=400)
        self.assertEqual(Meeting.objects.count(), 0)

    def test_duration_and_location(self):
        meeting = self.request()
        for bad in ({"duration": 20}, {"location": "  "}, {"location": "x" * 121}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                services.confirm(self.advisor, meeting, **{**slot(), **bad})
        for minutes in (15, 30, 45, 60):
            services.confirm(self.advisor, self.request(), **slot(duration=minutes))

    def test_an_expired_suggestion_cannot_be_accepted(self):
        meeting = self.suggested()
        with mock.patch("django.utils.timezone.now", return_value=meeting.starts_at + timedelta(minutes=1)):
            with self.assertRaises(ValidationError):
                services.accept_suggestion(self.student, meeting)

    def test_request_needs_an_advisor_for_the_cohort(self):
        lonely = make_student("70000010@student.uol.edu.pk", academics=self.academics,
                              cohort=cohort(self.academics, batch="other_batch"))
        with self.assertRaises(ValidationError):
            self.request(student=lonely)

    def test_inactive_cohort_takes_no_new_meetings(self):
        section = self.academics["section"]
        section.is_active = False
        section.save()
        with self.assertRaises(ValidationError):
            self.request()


class PrivacyTests(MeetingTestCase):
    def assert_blocked(self, user, url_names, pk):
        self.client.force_login(user)
        for url_name in url_names:
            with self.subTest(user=user.email, url=url_name):
                self.assertEqual(self.client.get(reverse(url_name, args=[pk])).status_code, 404)

    def test_other_students_and_advisors_get_404(self):
        meeting = self.request()
        for user in (self.classmate, self.outsider):
            self.assert_blocked(user, ["student_meeting_detail"], meeting.pk)
        for user in (self.other_advisor, self.near_advisor):
            self.assert_blocked(user, ["advisor_meeting_detail"], meeting.pk)

    def test_cr_and_gr_get_404_and_see_nothing_extra(self):
        meeting = self.request()
        batch, semester, section = self.cohort
        gr = make_student("70000011@student.uol.edu.pk", academics=self.academics, full_name="Girls Rep")
        CohortRepresentation.objects.create(batch=batch, semester=semester, section=section, cr=self.classmate, gr=gr)
        for user in (self.classmate, gr):
            self.assert_blocked(user, ["student_meeting_detail"], meeting.pk)
            self.assertNotContains(self.client.get(reverse("student_meetings")), REASON)
            for action in ("student_meeting_accept", "student_meeting_decline", "student_meeting_cancel"):
                self.assertEqual(self.client.post(reverse(action, args=[meeting.pk])).status_code, 404)

    def test_post_routes_of_another_cohort_are_404_and_change_nothing(self):
        meeting = self.request()
        self.client.force_login(self.other_advisor)
        for action in ("confirm", "suggest", "decline", "cancel"):
            response = self.client.post(reverse(f"advisor_meeting_{action}", args=[meeting.pk]), slot_post(action))
            self.assertEqual(response.status_code, 404)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.REQUESTED)

    def test_lists_are_scoped(self):
        self.request()
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("student_meetings")), REASON[:40])
        self.client.force_login(self.classmate)
        self.assertNotContains(self.client.get(reverse("student_meetings")), REASON[:40])
        self.client.force_login(self.advisor)
        self.assertContains(self.client.get(reverse("advisor_meetings")), "Ali Khan")
        self.client.force_login(self.other_advisor)
        self.assertNotContains(self.client.get(reverse("advisor_meetings")), "Ali Khan")

    def test_month_view_is_scoped(self):
        meeting = self.confirmed()
        local = timezone.localtime(meeting.starts_at).date()
        query = {"month": f"{local:%Y-%m}", "day": local.isoformat()}
        self.client.force_login(self.classmate)
        self.assertNotContains(self.client.get(reverse("student_meetings_month"), query), REASON[:40])
        self.client.force_login(self.other_advisor)
        self.assertNotContains(self.client.get(reverse("advisor_meetings_month"), query), "Ali Khan")

    def test_role_routes(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("advisor_meetings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("super_admin_meetings")).status_code, 403)
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(reverse("student_meetings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("super_admin_meetings")).status_code, 403)

    def test_schedule_form_offers_only_assigned_students(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_meeting_schedule"))
        self.assertContains(response, "Ali Khan")
        self.assertNotContains(response, "Other Section ·")
        day = (timezone.localdate() + timedelta(days=3)).isoformat()
        response = self.client.post(reverse("advisor_meeting_schedule"), {
            "student": self.outsider.pk, "reason": REASON, "date": day, "time": "10:00", "duration": 30, "location": "Room 1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Meeting.objects.count(), 0)


class SuperAdminTests(MeetingTestCase):
    def test_sees_all_read_only_with_filters(self):
        self.request()
        other = services.confirm(self.other_advisor, self.request(student=self.outsider, reason="Another cohort's meeting."), **slot())
        self.client.force_login(self.admin)
        url = reverse("super_admin_meetings")
        response = self.client.get(url)
        self.assertContains(response, "Ali Khan")
        self.assertContains(response, "Other Section")
        main = response.content.decode().split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('method="post"', main)  # the header's sign-out form is outside the page
        filtered = self.client.get(url, {"status": Status.CONFIRMED})
        self.assertContains(filtered, "Other Section")
        self.assertNotContains(filtered, "Ali Khan")
        value = f"{other.batch_id}.{other.semester_id}.{other.section_id}"
        by_cohort = self.client.get(url, {"cohort": value})
        self.assertContains(by_cohort, "Other Section")
        self.assertNotContains(by_cohort, "Ali Khan")
        self.assertContains(self.client.get(url, {"status": "nonsense", "cohort": "1.2"}), "Ali Khan")
        self.assertEqual(Meeting.objects.filter(status=Status.REQUESTED).count(), 1)


class NotificationTests(MeetingTestCase):
    def test_each_advisor_action_notifies_the_student(self):
        services.confirm(self.advisor, self.request(), **slot())
        services.suggest(self.advisor, self.request(), **slot())
        services.decline(self.advisor, self.request(), "Not needed.")
        services.cancel(self.advisor, self.confirmed(), "Something came up.")
        services.schedule(self.advisor, self.student, reason=REASON, **slot())
        types = list(self.notices().values_list("event_type", flat=True))
        for event_type, count in (("meeting.confirmed", 3), ("meeting.time_suggested", 1),
                                  ("meeting.declined", 1), ("meeting.cancelled", 1)):
            self.assertEqual(types.count(event_type), count, event_type)

    def test_one_meeting_can_notify_more_than_once(self):
        meeting = self.confirmed()
        services.cancel(self.advisor, meeting, "Something came up.")
        self.assertEqual(self.notices().count(), 2)

    def test_the_students_own_actions_do_not_notify(self):
        services.accept_suggestion(self.student, self.suggested())
        services.decline_suggestion(self.student, self.suggested())
        self.assertEqual(self.notices().count(), 2)  # only the two suggestions
        before = self.notices().count()
        meeting = Meeting.objects.filter(status=Status.CONFIRMED).first()
        services.cancel(self.student, meeting, "Something came up.")
        self.assertEqual(self.notices().count(), before)

    def test_nobody_else_is_notified(self):
        self.confirmed()
        self.assertEqual(Notification.objects.exclude(recipient=self.student).count(), 0)

    def test_notification_opens_the_meeting(self):
        meeting = self.confirmed()
        notification = self.notices().get()
        self.client.force_login(self.student)
        response = self.client.post(reverse("notification_open", args=[notification.pk]))
        self.assertRedirects(response, reverse("student_meeting_detail", args=[meeting.pk]), status_code=303)


class GoogleCalendarTests(MeetingTestCase):
    def test_url_contents_are_in_utc(self):
        start = local_datetime(timezone.localdate() + timedelta(days=3), time(10, 0))
        meeting = services.confirm(self.advisor, self.request(), starts_at=start, duration=45, location="Room 204, CS Block")
        parsed = urlparse(google_calendar_url(meeting, self.student))
        query = parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://calendar.google.com/calendar/render")
        self.assertEqual(query["action"], ["TEMPLATE"])
        self.assertEqual(query["text"], ["Meeting with First Advisor"])
        self.assertEqual(query["location"], ["Room 204, CS Block"])
        utc_start = start.astimezone(dt_timezone.utc)  # Karachi is UTC+5
        self.assertEqual(utc_start.hour, 5)
        expected = f"{utc_start:%Y%m%dT%H%M%SZ}/{utc_start + timedelta(minutes=45):%Y%m%dT%H%M%SZ}"
        self.assertEqual(query["dates"], [expected])
        self.assertIn("details", query)

    def test_the_private_reason_is_not_sent_to_google(self):
        self.assertNotIn("course", google_calendar_url(self.confirmed(), self.student))

    def test_advisor_link_names_the_student(self):
        query = parse_qs(urlparse(google_calendar_url(self.confirmed(), self.advisor)).query)
        self.assertEqual(query["text"], ["Meeting with Ali Khan"])

    def test_link_only_on_confirmed_meetings(self):
        self.client.force_login(self.student)
        pending = self.suggested()
        self.assertNotContains(self.client.get(reverse("student_meeting_detail", args=[pending.pk])), "Add to Google Calendar")
        confirmed = self.confirmed()
        self.assertContains(self.client.get(reverse("student_meeting_detail", args=[confirmed.pk])), "Add to Google Calendar")
        # The list rows are links to the detail; the home's upcoming card carries the link too.
        self.assertContains(self.client.get(reverse("student_home")), "calendar.google.com/calendar/render?action=TEMPLATE")


class MonthViewTests(MeetingTestCase):
    def test_parse_month(self):
        today = date(2026, 11, 23)
        self.assertEqual(parse_month("2027-02", today), (2027, 2))
        for bad in (None, "", "2026-13", "2026-00", "2026-1", "abcd-ef", "1999-01", "2101-01", "2026-11-01", "٢٠٢٦-١١"):
            with self.subTest(value=bad):
                self.assertEqual(parse_month(bad, today), (2026, 11))

    def test_invalid_month_shows_the_current_month(self):
        self.client.force_login(self.student)
        today = timezone.localdate()
        response = self.client.get(reverse("student_meetings_month"), {"month": "not-a-month"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, today.strftime("%B %Y"))

    def test_previous_and_next_cross_the_year(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_meetings_month"), {"month": "2027-01"})
        self.assertContains(response, 'href="?month=2026-12"')
        self.assertContains(response, 'href="?month=2027-02"')
        response = self.client.get(reverse("advisor_meetings_month"), {"month": "2026-12"})
        self.assertContains(response, 'href="?month=2027-01"')

    def test_grid_starts_on_monday_and_mutes_other_months(self):
        month = build_month(Meeting.objects.none(), "2026-11", None)
        self.assertEqual(month["weeks"][0][0]["date"], date(2026, 10, 26))
        self.assertFalse(month["weeks"][0][0]["in_month"])
        self.assertTrue(month["weeks"][0][6]["in_month"])

    def test_day_shows_count_and_lists_its_meetings(self):
        first = self.confirmed()
        self.confirmed(starts_at=future(hour=14))
        local = timezone.localtime(first.starts_at).date()
        self.client.force_login(self.student)
        query = {"month": f"{local:%Y-%m}", "day": local.isoformat()}
        response = self.client.get(reverse("student_meetings_month"), query)
        self.assertContains(response, ", 2 meetings")
        self.assertContains(response, 'class="sa-cal-count"')
        self.assertEqual([m.pk for m in response.context["month"]["day_meetings"]],
                         [first.pk, Meeting.objects.exclude(pk=first.pk).get().pk])

    def test_only_confirmed_meetings_are_counted(self):
        meeting = self.suggested()
        local = timezone.localtime(meeting.starts_at).date()
        month = build_month(Meeting.objects.all(), f"{local:%Y-%m}", local.isoformat())
        self.assertEqual(sum(cell["count"] for week in month["weeks"] for cell in week), 0)

    def test_invalid_or_foreign_day_is_ignored(self):
        self.client.force_login(self.student)
        for day in ("nonsense", "2020-01-01"):
            response = self.client.get(reverse("student_meetings_month"), {"month": "2030-05", "day": day})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context["month"]["selected"])


class OverlapTests(MeetingTestCase):
    def test_warning_text(self):
        self.confirmed()
        warnings = overlap_warnings(self.advisor, future(minute=15), 30)
        self.assertEqual(warnings, ["You already have a meeting from 10:00 to 10:30 with Ali Khan."])

    def test_touching_other_day_and_other_advisor_do_not_warn(self):
        self.confirmed()
        self.assertEqual(overlap_warnings(self.advisor, future(minute=30), 30), [])
        self.assertEqual(overlap_warnings(self.advisor, future(days=4), 30), [])
        self.assertEqual(overlap_warnings(self.co_advisor, future(), 30), [])

    def test_only_confirmed_meetings_count(self):
        self.suggested()
        self.assertEqual(overlap_warnings(self.advisor, future(), 30), [])
        services.cancel(self.student, self.confirmed(), "Something came up.")
        self.assertEqual(overlap_warnings(self.advisor, future(), 30), [])

    def test_names_every_clash_even_behind_a_longer_meeting(self):
        self.confirmed(duration=60)
        self.confirmed(starts_at=future(minute=20), duration=30)
        self.assertEqual(len(overlap_warnings(self.advisor, future(minute=10), 15)), 2)

    def test_confirm_view_warns_first_then_allows(self):
        self.confirmed()
        meeting = self.request()
        self.client.force_login(self.advisor)
        url = reverse("advisor_meeting_confirm", args=[meeting.pk])
        response = self.client.post(url, slot_post("confirm", minute=15))
        self.assertContains(response, "You already have a meeting from 10:00 to 10:30")
        self.assertContains(response, "Confirm anyway")
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.REQUESTED)
        token = response.context["overlap_token"]
        response = self.client.post(url, slot_post("confirm", minute=15, overlap_ack=token))
        self.assertRedirects(response, reverse("advisor_meeting_detail", args=[meeting.pk]))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.CONFIRMED)

    def test_changing_the_time_warns_again(self):
        self.confirmed()
        meeting = self.request()
        self.client.force_login(self.advisor)
        url = reverse("advisor_meeting_confirm", args=[meeting.pk])
        token = self.client.post(url, slot_post("confirm", minute=15)).context["overlap_token"]
        response = self.client.post(url, slot_post("confirm", minute=20, overlap_ack=token))
        self.assertContains(response, "You already have a meeting")
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.REQUESTED)

    def test_schedule_view_warns_first_then_allows(self):
        self.confirmed()
        self.client.force_login(self.advisor)
        day = (timezone.localdate() + timedelta(days=3)).isoformat()
        data = {"student": self.classmate.pk, "reason": REASON, "date": day, "time": "10:10", "duration": 30, "location": "Room 1"}
        url = reverse("advisor_meeting_schedule")
        response = self.client.post(url, data)
        self.assertContains(response, "You already have a meeting from 10:00 to 10:30")
        self.assertContains(response, "Schedule anyway")
        self.assertFalse(Meeting.objects.filter(student=self.classmate).exists())
        self.client.post(url, {**data, "overlap_ack": response.context["overlap_token"]})
        self.assertTrue(Meeting.objects.filter(student=self.classmate, status=Status.CONFIRMED).exists())


class PageFlowTests(MeetingTestCase):
    def test_student_requests_through_the_page(self):
        self.client.force_login(self.student)
        day = (timezone.localdate() + timedelta(days=2)).isoformat()
        response = self.client.post(reverse("student_meetings"), {"reason": REASON, "date": day, "time": "11:30"})
        self.assertRedirects(response, reverse("student_meetings"))
        meeting = Meeting.objects.get()
        self.assertEqual(timezone.localtime(meeting.preferred_at).strftime("%H:%M"), "11:30")  # Asia/Karachi

    def test_advisor_flow_through_the_pages(self):
        self.client.force_login(self.advisor)
        meeting = self.request()
        self.assertContains(self.client.get(reverse("advisor_meetings")), "Needs a decision")
        self.client.post(reverse("advisor_meeting_suggest", args=[meeting.pk]), slot_post("suggest", **{"suggest-note": "Is this fine?"}))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.TIME_SUGGESTED)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("student_meetings")), "Waiting for reply")
        self.assertContains(self.client.get(reverse("student_meeting_detail", args=[meeting.pk])), "Accept")
        self.client.post(reverse("student_meeting_accept", args=[meeting.pk]))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.CONFIRMED)
        response = self.client.post(reverse("student_meeting_cancel", args=[meeting.pk]), {"cancel-reason": ""})
        self.assertEqual(response.status_code, 400)
        self.client.post(reverse("student_meeting_cancel", args=[meeting.pk]), {"cancel-reason": "Something came up."})
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.CANCELLED)

    def test_advisor_decline_needs_a_reason_on_the_page(self):
        meeting = self.request()
        self.client.force_login(self.advisor)
        url = reverse("advisor_meeting_decline", args=[meeting.pk])
        self.assertEqual(self.client.post(url, {"decline-reason": " "}).status_code, 400)
        self.client.post(url, {"decline-reason": "Please use the complaints page."})
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.DECLINED)

    def test_second_advisor_acting_late_is_told(self):
        meeting = self.request()
        services.confirm(self.co_advisor, meeting, **slot())
        self.client.force_login(self.advisor)
        response = self.client.post(reverse("advisor_meeting_confirm", args=[meeting.pk]), slot_post("confirm"), follow=True)
        self.assertContains(response, "already been handled")
        meeting.refresh_from_db()
        self.assertEqual(meeting.advisor, self.co_advisor)

    def test_groups_today_tomorrow_and_dates_in_start_order(self):
        today = date(2026, 11, 23)
        def at(day, hour):
            return Meeting(status=Status.REQUESTED, preferred_at=local_datetime(day, time(hour)))
        ordered = [at(today, 9), at(today, 14), at(date(2026, 11, 24), 9), at(date(2026, 11, 27), 9)]
        groups = group_by_day(ordered, today)
        self.assertEqual([g["label"] for g in groups], ["Today", "Tomorrow", "Friday 27 November"])
        self.assertEqual(len(groups[0]["meetings"]), 2)

    def test_upcoming_is_sorted_and_past_goes_to_closed(self):
        late = services.schedule(self.advisor, self.student, reason=REASON, **slot(days=5))
        early = services.schedule(self.advisor, self.student, reason=REASON, **slot(days=2))
        declined = services.decline(self.advisor, self.request(), "Not needed.")
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_meetings"))
        # Polish v2 list groups: Waiting for reply · Upcoming · Past and closed.
        groups = dict(response.context["groups"])
        self.assertEqual([m.pk for m in groups["Upcoming"]], [early.pk, late.pk])
        self.assertEqual([m.pk for m in groups["Past and closed"]], [declined.pk])


class StudentHomeTests(MeetingTestCase):
    def test_home_shows_meeting_updates_and_the_request_action(self):
        self.confirmed()
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_home"))
        self.assertContains(response, "Meeting confirmed")
        self.assertContains(response, "Request meeting")
        self.assertContains(response, reverse("student_meetings"))

    def test_updates_are_limited_to_five_newest_first(self):
        for _ in range(7):
            self.confirmed()
        updates = student_home_updates(self.student)
        self.assertEqual(len(updates), 5)
        self.assertEqual([u.when for u in updates], sorted((u.when for u in updates), reverse=True))

    def test_a_request_alone_is_not_an_update(self):
        self.request()
        self.assertEqual(student_home_updates(self.student), [])

    def test_navigation_for_each_role(self):
        for user, url in ((self.student, "student_meetings"), (self.advisor, "advisor_meetings"), (self.admin, "super_admin_meetings")):
            self.client.force_login(user)
            response = self.client.get(reverse(url))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'href="{reverse(url)}"')


class SeedTests(TestCase):
    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[])
    def test_seed_twice_covers_every_status(self):
        call_command("seed_demo", stdout=StringIO())
        counts = (Meeting.objects.count(), MeetingEvent.objects.count())
        self.assertGreaterEqual(counts[0], 10)
        self.assertEqual(set(Meeting.objects.values_list("status", flat=True)), set(Status.values))
        self.assertEqual(set(Meeting.objects.values_list("section__name", flat=True)), {"DEMO-A", "DEMO-B"})
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual((Meeting.objects.count(), MeetingEvent.objects.count()), counts)

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[])
    def test_demo_advisor_has_an_overlap_to_show(self):
        call_command("seed_demo", stdout=StringIO())
        request = Meeting.objects.get(status=Status.REQUESTED, reason__startswith="I would like advice on choosing")
        advisor = Meeting.objects.get(reason__startswith="Let us review your elective").advisor
        self.assertEqual(advisor.email, "demo.advisor@uol.edu.pk")
        self.assertEqual(len(overlap_warnings(advisor, request.preferred_at, 30)), 2)

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=["head@example.com", "teacher@example.com"])
    def test_uses_the_demo_staff_advisor_when_set(self):
        call_command("seed_demo", stdout=StringIO())
        advisor = Meeting.objects.get(reason__startswith="Let us review your elective").advisor
        self.assertEqual(advisor.email, "teacher@example.com")

    @override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[])
    def test_seeded_on_a_weekend_still_works(self):
        saturday = timezone.make_aware(datetime(2026, 11, 28, 9, 0), timezone.get_default_timezone())
        with mock.patch("meetings.tests.test_meetings.timezone.now", return_value=saturday):
            call_command("seed_demo", stdout=StringIO())
        for meeting in Meeting.objects.exclude(starts_at=None):
            self.assertLess(timezone.localtime(meeting.starts_at).weekday(), 5)
