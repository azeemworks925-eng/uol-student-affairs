"""Student Voice: privacy, the one-answer rule, validation, notifications, oversight and navigation."""

from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CohortRepresentation
from accounts.tests.helpers import OTHER_STUDENT_EMAIL, cohort, make_academics, make_advisor, make_student, make_super_admin
from complaints import services as complaint_services
from complaints.models import ComplaintCategory
from notifications import services as notification_services
from notifications.models import Notification
from voice import services
from voice.admin import SubmissionAdmin
from voice.models import ProtectedSubmissionError, Submission
from voice.permissions import visible_submissions
from voice.presentation import student_home_updates

Type = Submission.Type
Status = Submission.Status
TEXT = "When will the date sheet be published?"


class VoiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.cohort = cohort(cls.academics)
        cls.other_cohort = cohort(cls.academics, section="other_section")
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=cls.academics, full_name="Sara Classmate")
        cls.advisor = make_advisor(cohorts=[cls.cohort], full_name="First Advisor")
        cls.co_advisor = make_advisor("co@uol.edu.pk", cohorts=[cls.cohort], full_name="Second Advisor")
        cls.other_advisor = make_advisor("other@uol.edu.pk", cohorts=[cls.other_cohort], full_name="Other Advisor")
        # Same batch and semester but another section, and same section in another semester.
        cls.near_advisor = make_advisor(
            "near@uol.edu.pk", cohorts=[cohort(cls.academics, semester="other_semester")], full_name="Near Advisor"
        )
        cls.admin = make_super_admin()

    def submit(self, kind=Type.QUESTION, text=TEXT, student=None):
        return services.submit(student or self.student, type=kind, text=text)


class SubmissionRuleTests(VoiceTestCase):
    def test_exactly_three_types(self):
        self.assertEqual(Type.labels, ["Idea", "Question", "Feedback"])
        with self.assertRaises(ValidationError):
            self.submit("appreciation")

    def test_length_limits_after_trimming(self):
        for text in ("", "   ", "too short", " " * 5 + "123456789" + " " * 5, "x" * 2001):
            with self.subTest(length=len(text)), self.assertRaises(ValidationError):
                self.submit(text=text)
        self.assertEqual(len(self.submit(text="x" * 10).text), 10)
        self.assertEqual(len(self.submit(text="x" * 2000).text), 2000)

    def test_cohort_comes_from_the_profile_and_stays(self):
        submission = self.submit()
        profile = self.student.student_profile
        profile.section = self.academics["other_section"]
        profile.save()
        submission.refresh_from_db()
        self.assertEqual(submission.section, self.academics["section"])
        self.assertIn(submission, visible_submissions(self.advisor))
        self.assertNotIn(submission, visible_submissions(self.other_advisor))

    def test_only_students_can_submit(self):
        for user in (self.advisor, self.admin):
            with self.subTest(role=user.role), self.assertRaises(PermissionDenied):
                services.submit(user, type=Type.IDEA, text=TEXT)

    def test_text_cannot_be_changed_and_records_cannot_be_deleted(self):
        submission = self.submit()
        submission.text = "A completely different message."
        with self.assertRaises(ProtectedSubmissionError):
            submission.save()
        with self.assertRaises(ProtectedSubmissionError):
            Submission.objects.get(pk=submission.pk).delete()
        with self.assertRaises(ProtectedSubmissionError):
            Submission.objects.all().delete()
        with self.assertRaises(ProtectedSubmissionError):
            Submission.objects.all().update(text="Changed in bulk here.")

    def test_database_refuses_an_impossible_status(self):
        submission = self.submit()
        submission.status = Status.REVIEWED  # a Question is never Reviewed
        with self.assertRaises(IntegrityError), transaction.atomic():
            submission.save(update_fields=["status"])


class AnswerRuleTests(VoiceTestCase):
    def test_question_gets_one_answer(self):
        submission = services.answer(self.advisor, self.submit(), "On Friday.")
        self.assertEqual(submission.status, Status.ANSWERED)
        with self.assertRaises(ValidationError):
            services.answer(self.co_advisor, submission, "A second answer.")
        submission.refresh_from_db()
        self.assertEqual(submission.answer, "On Friday.")
        self.assertEqual(submission.answered_by, self.advisor)

    def test_stale_object_cannot_answer_twice(self):
        submission = self.submit()
        stale = Submission.objects.get(pk=submission.pk)
        services.answer(self.advisor, submission, "First answer.")
        with self.assertRaises(ValidationError):
            services.answer(self.co_advisor, stale, "Second answer.")
        self.assertEqual(Submission.objects.get(pk=submission.pk).answer, "First answer.")

    def test_saved_answer_cannot_be_overwritten(self):
        submission = services.answer(self.advisor, self.submit(), "On Friday.")
        submission.answer = "Changed."
        with self.assertRaises(ProtectedSubmissionError):
            submission.save()

    def test_question_cannot_be_marked_reviewed(self):
        with self.assertRaises(ValidationError):
            services.mark_reviewed(self.advisor, self.submit())

    def test_idea_and_feedback_can_be_reviewed_without_a_reply(self):
        for kind in (Type.IDEA, Type.FEEDBACK):
            with self.subTest(kind=kind):
                submission = services.mark_reviewed(self.advisor, self.submit(kind))
                self.assertEqual(submission.status, Status.REVIEWED)
                self.assertEqual(submission.answer, "")
                with self.assertRaises(ValidationError):
                    services.mark_reviewed(self.co_advisor, submission)

    def test_reviewed_idea_can_get_one_reply(self):
        submission = services.mark_reviewed(self.advisor, self.submit(Type.IDEA))
        submission = services.answer(self.co_advisor, submission, "Thank you for this.")
        self.assertEqual(submission.status, Status.REVIEWED)
        self.assertEqual(submission.reviewed_by, self.advisor)
        with self.assertRaises(ValidationError):
            services.answer(self.advisor, submission, "Another reply.")

    def test_reply_marks_a_waiting_idea_reviewed(self):
        submission = services.answer(self.advisor, self.submit(Type.FEEDBACK), "Thank you.")
        self.assertEqual(submission.status, Status.REVIEWED)
        self.assertEqual(submission.reviewed_by, self.advisor)

    def test_blank_and_too_long_answers_are_refused(self):
        submission = self.submit()
        for text in ("", "   ", "x" * 2001):
            with self.subTest(length=len(text)), self.assertRaises(ValidationError):
                services.answer(self.advisor, submission, text)

    def test_every_advisor_of_the_exact_cohort_can_act(self):
        services.answer(self.co_advisor, self.submit(), "Answered by the second advisor.")

    def test_others_cannot_act(self):
        submission = self.submit(Type.IDEA)
        for user in (self.other_advisor, self.near_advisor, self.admin, self.student, self.classmate):
            with self.subTest(user=user.email):
                with self.assertRaises(PermissionDenied):
                    services.answer(user, submission, "Not allowed.")
                with self.assertRaises(PermissionDenied):
                    services.mark_reviewed(user, submission)


class PrivacyTests(VoiceTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.submission = services.submit(cls.student, type=Type.QUESTION, text=TEXT)
        cls.cr = make_student("11112222@student.uol.edu.pk", academics=cls.academics, full_name="Class Rep")
        cls.gr = make_student("33334444@student.uol.edu.pk", academics=cls.academics, full_name="Girls Rep")
        batch, semester, section = cls.cohort
        CohortRepresentation.objects.create(batch=batch, semester=semester, section=section, cr=cls.cr, gr=cls.gr)

    def test_other_students_and_representatives_get_404(self):
        url = reverse("student_voice_detail", args=[self.submission.pk])
        for user in (self.classmate, self.cr, self.gr):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertNotContains(self.client.get(reverse("student_voice")), TEXT)

    def test_other_cohort_advisors_get_404(self):
        for user in (self.other_advisor, self.near_advisor):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("advisor_voice_detail", args=[self.submission.pk])).status_code, 404)
                for route in ("advisor_voice_answer", "advisor_voice_review"):
                    response = self.client.post(reverse(route, args=[self.submission.pk]), {"answer": "Not allowed."})
                    self.assertEqual(response.status_code, 404)
                self.assertNotContains(self.client.get(reverse("advisor_voice")), TEXT)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Status.WAITING)

    def test_missing_record_is_also_404(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("student_voice_detail", args=[999999])).status_code, 404)

    def test_owner_and_assigned_staff_can_open_it(self):
        for user, route in ((self.student, "student_voice_detail"), (self.advisor, "advisor_voice_detail"),
                            (self.co_advisor, "advisor_voice_detail"), (self.admin, "super_admin_voice_detail")):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertContains(self.client.get(reverse(route, args=[self.submission.pk])), TEXT)

    def test_roles_cannot_open_each_others_pages(self):
        for user, route in ((self.student, "advisor_voice"), (self.student, "super_admin_voice"),
                            (self.advisor, "student_voice"), (self.advisor, "super_admin_voice"),
                            (self.admin, "student_voice"), (self.admin, "advisor_voice")):
            with self.subTest(user=user.role, route=route):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)

    def test_inactive_user_sees_nothing(self):
        self.advisor.is_active = False
        self.assertFalse(visible_submissions(self.advisor).exists())

    def test_cohort_filter_cannot_widen_an_advisors_list(self):
        batch, semester, section = self.cohort
        self.client.force_login(self.other_advisor)
        response = self.client.get(reverse("advisor_voice"), {"cohort": f"{batch.pk}.{semester.pk}.{section.pk}"})
        self.assertNotContains(response, TEXT)


class StudentPageTests(VoiceTestCase):
    def setUp(self):
        self.client.force_login(self.student)
        self.url = reverse("student_voice")

    def test_friendly_empty_state(self):
        self.assertContains(self.client.get(self.url), "Nothing here yet.")

    def test_submit_then_listed(self):
        response = self.client.post(self.url, {"type": "idea", "text": "A quiet study room would help."}, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "A quiet study room would help.")
        self.assertContains(response, "Waiting")
        self.assertEqual(Submission.objects.get().student, self.student)

    def test_form_cannot_choose_the_student_or_status(self):
        self.client.post(self.url, {"type": "idea", "text": "A quiet study room would help.",
                                    "student": self.classmate.pk, "status": "answered"})
        submission = Submission.objects.get()
        self.assertEqual((submission.student, submission.status), (self.student, Status.WAITING))

    def test_invalid_input_is_shown_and_not_saved(self):
        for data in ({"type": "idea", "text": "short"}, {"type": "appreciation", "text": TEXT},
                     {"text": TEXT}, {"type": "question", "text": "y" * 2001}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertFalse(Submission.objects.exists())

    def test_answer_is_shown_beside_the_question(self):
        services.answer(self.advisor, self.submit(), "It comes out on Friday.")
        response = self.client.get(self.url)
        self.assertContains(response, "Official answer")
        self.assertContains(response, "It comes out on Friday.")
        self.assertContains(response, "Answered")
        self.assertNotContains(response, "First Advisor")  # staff appear by role only

    def test_newest_first(self):
        first = self.submit(text="The first message here.")
        second = self.submit(text="The second message here.")
        self.assertEqual([s.pk for s in self.client.get(self.url).context["page"]], [second.pk, first.pk])


class AdvisorWorkspaceTests(VoiceTestCase):
    def setUp(self):
        self.client.force_login(self.advisor)
        self.url = reverse("advisor_voice")

    def test_answer_through_the_page(self):
        submission = self.submit()
        answer_url = reverse("advisor_voice_answer", args=[submission.pk])
        response = self.client.post(answer_url, {"answer": "On Friday."}, follow=True)
        self.assertContains(response, "The student has been notified.")
        self.assertNotContains(response, 'name="answer"')  # the form is gone once answered
        self.client.post(answer_url, {"answer": "Changed my mind."})
        submission.refresh_from_db()
        self.assertEqual(submission.answer, "On Friday.")

    def test_blank_answer_shows_an_error(self):
        submission = self.submit()
        response = self.client.post(reverse("advisor_voice_answer", args=[submission.pk]), {"answer": "  "})
        self.assertContains(response, "Write your response.", status_code=400)

    def test_mark_reviewed_button_only_for_waiting_ideas_and_feedback(self):
        idea, question = self.submit(Type.IDEA), self.submit(Type.QUESTION)
        self.assertNotContains(self.client.get(reverse("advisor_voice_detail", args=[question.pk])), "Mark reviewed")
        self.assertContains(self.client.get(reverse("advisor_voice_detail", args=[idea.pk])), "Mark reviewed")
        response = self.client.post(reverse("advisor_voice_review", args=[idea.pk]), follow=True)
        self.assertContains(response, "Marked as reviewed.")
        self.assertNotContains(response, "Mark reviewed")
        self.assertContains(response, "Write a reply")  # the optional reply is still available

    def test_filters(self):
        idea, question = self.submit(Type.IDEA), self.submit(Type.QUESTION)
        services.mark_reviewed(self.advisor, idea)
        rows = lambda **params: [s.pk for s in self.client.get(self.url, params).context["page"]]
        self.assertEqual(rows(type="idea"), [idea.pk])
        self.assertEqual(rows(status="waiting"), [question.pk])
        self.assertEqual(rows(type="question", status="reviewed"), [])
        batch, semester, section = self.cohort
        self.assertEqual(len(rows(cohort=f"{batch.pk}.{semester.pk}.{section.pk}")), 2)
        self.assertEqual(len(rows(type="nonsense", cohort="1.2.3", status="nope")), 2)  # invalid values are ignored

    def test_sorted_with_merge_sort_newest_first_by_default(self):
        first, second = self.submit(text="The first message here."), self.submit(text="The second message here.")
        with mock.patch("voice.presentation.merge_sort", wraps=__import__("dsa.sorting").sorting.merge_sort) as sort:
            self.assertEqual([s.pk for s in self.client.get(self.url).context["page"]], [second.pk, first.pk])
        sort.assert_called()
        self.assertEqual([s.pk for s in self.client.get(self.url, {"sort": "oldest"}).context["page"]], [first.pk, second.pk])

    def test_no_assignments(self):
        self.client.force_login(make_advisor("none@uol.edu.pk"))
        self.assertContains(self.client.get(self.url), "No cohorts are assigned to you yet.")


class NotificationTests(VoiceTestCase):
    def test_answer_notifies_only_the_student_and_links_to_the_submission(self):
        submission = services.answer(self.advisor, self.submit(), "On Friday.")
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.student)
        self.assertEqual(notification.event_type, "voice.answered")
        self.assertEqual(notification.title, "Your question has an answer")
        self.assertNotIn("First Advisor", notification.body)
        self.assertEqual(notification_services.destination_url(notification),
                         reverse("student_voice_detail", args=[submission.pk]))

    def test_opening_it_reaches_the_submission(self):
        submission = services.answer(self.advisor, self.submit(), "On Friday.")
        self.client.force_login(self.student)
        response = self.client.post(reverse("notification_open", args=[Notification.objects.get().pk]), follow=True)
        self.assertRedirects(response, reverse("student_voice_detail", args=[submission.pk]), status_code=303)
        self.assertContains(response, "On Friday.")

    def test_reply_notifies(self):
        services.answer(self.advisor, self.submit(Type.FEEDBACK), "Thank you.")
        notification = Notification.objects.get()
        self.assertEqual((notification.event_type, notification.title), ("voice.replied", "Your feedback has a reply"))

    def test_submit_and_review_do_not_notify(self):
        services.mark_reviewed(self.advisor, self.submit(Type.IDEA))
        self.assertFalse(Notification.objects.exists())

    def test_failed_notification_rolls_back_the_answer(self):
        submission = self.submit()
        with mock.patch("voice.services.notify_student", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                services.answer(self.advisor, submission, "On Friday.")
        submission.refresh_from_db()
        self.assertEqual((submission.answer, submission.status), ("", Status.WAITING))


class SuperAdminTests(VoiceTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_sees_every_cohort_with_filters(self):
        other = make_student("55556666@student.uol.edu.pk", academics=self.academics, cohort=self.other_cohort)
        mine, theirs = self.submit(), self.submit(Type.IDEA, "An idea from another cohort.", student=other)
        url = reverse("super_admin_voice")
        self.assertEqual({s.pk for s in self.client.get(url).context["page"]}, {mine.pk, theirs.pk})
        self.assertEqual([s.pk for s in self.client.get(url, {"type": "idea"}).context["page"]], [theirs.pk])
        batch, semester, section = self.other_cohort
        value = f"{batch.pk}.{semester.pk}.{section.pk}"
        self.assertEqual([s.pk for s in self.client.get(url, {"cohort": value}).context["page"]], [theirs.pk])

    def test_page_is_read_only(self):
        submission = self.submit(Type.IDEA)
        url = reverse("super_admin_voice_detail", args=[submission.pk])
        response = self.client.get(url)
        self.assertContains(response, "Read-only oversight")
        self.assertNotContains(response, 'name="answer"')
        self.assertNotContains(response, "Mark reviewed")
        self.assertNotIn('method="post"', response.content.decode().split("<main")[1].split("</main>")[0])  # the whole page content
        self.client.post(url, {"answer": "Not allowed."})
        for route in ("advisor_voice_answer", "advisor_voice_review"):
            self.assertEqual(self.client.post(reverse(route, args=[submission.pk]), {"answer": "No."}).status_code, 403)
        submission.refresh_from_db()
        self.assertEqual((submission.status, submission.answer), (Status.WAITING, ""))

    def test_django_admin_is_read_only(self):
        request = RequestFactory().get("/")
        request.user = self.admin
        admin = SubmissionAdmin(Submission, site)
        self.assertFalse(admin.has_add_permission(request))
        self.assertFalse(admin.has_change_permission(request))
        self.assertFalse(admin.has_delete_permission(request))
        self.assertTrue(admin.has_view_permission(request))
        submission = self.submit()
        response = self.client.get(reverse("admin:voice_submission_changelist"))
        self.assertContains(response, f"/admin/voice/submission/{submission.pk}/change/")
        self.assertEqual(self.client.get(reverse("admin:voice_submission_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:voice_submission_delete", args=[submission.pk])).status_code, 403)

    def test_no_section_on_the_super_admin_dashboard(self):  # DEC-254: navigation only
        html = self.client.get(reverse("super_admin_home")).content.decode()
        self.assertNotIn("Student Voice</h", html)


class NavigationTests(VoiceTestCase):
    def test_each_role_sees_the_item(self):
        for user, home, route in ((self.student, "student_home", "student_voice"),
                                  (self.advisor, "advisor_home", "advisor_voice"),
                                  (self.admin, "super_admin_home", "super_admin_voice")):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                labels = {i["label"]: i["url"] for i in self.client.get(reverse(home)).context["sa_nav_items"]}
                self.assertEqual(labels["Student Voice"], reverse(route))

    def test_item_is_current_on_the_detail_page(self):
        submission = self.submit()
        self.client.force_login(self.advisor)
        items = self.client.get(reverse("advisor_voice_detail", args=[submission.pk])).context["sa_nav_items"]
        self.assertTrue(next(i for i in items if i["label"] == "Student Voice")["current"])

    def test_quick_access_links_here(self):
        self.client.force_login(self.student)
        quick = {i["label"]: i["url"] for i in self.client.get(reverse("student_home")).context["quick_access"]}
        self.assertEqual(quick["Student Voice"], reverse("student_voice"))


class StudentHomeUpdateTests(VoiceTestCase):
    def test_answers_merge_with_complaint_updates_newest_first(self):
        category = ComplaintCategory.objects.create(name="Voice Test Category", position=50)
        complaint = complaint_services.submit_complaint(self.student, category=category, title="Lab clash",
                                                        description="Two labs clash every week.")
        now = timezone.now()
        question = self.submit()
        with mock.patch("django.utils.timezone.now", return_value=now - timedelta(days=3)):
            complaint_services.respond(self.advisor, complaint, "Older complaint response.")
        with mock.patch("django.utils.timezone.now", return_value=now - timedelta(days=2)):
            services.answer(self.advisor, question, "Middle answer.")
        with mock.patch("django.utils.timezone.now", return_value=now - timedelta(days=1)):
            complaint_services.respond(self.advisor, complaint, "Newer complaint response.")
        updates = student_home_updates(self.student)
        self.assertEqual([u.reference for u in updates], [complaint.reference, "Student Voice", complaint.reference])
        self.assertTrue(updates[1].is_new)
        self.assertEqual(updates[1].url, reverse("student_voice_detail", args=[question.pk]))

    def test_at_most_five(self):
        for number in range(7):
            services.answer(self.advisor, self.submit(text=f"Question number {number} here."), "Answer.")
        self.client.force_login(self.student)
        self.assertEqual(len(self.client.get(reverse("student_home")).context["updates"]), 5)

    def test_review_without_a_reply_is_not_an_update(self):
        services.mark_reviewed(self.advisor, self.submit(Type.IDEA))
        self.assertEqual(student_home_updates(self.student), [])

    def test_other_students_answers_are_not_included(self):
        services.answer(self.advisor, self.submit(student=self.classmate), "For the classmate.")
        self.assertEqual(student_home_updates(self.student), [])
