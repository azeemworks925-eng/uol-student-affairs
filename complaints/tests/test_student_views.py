"""Student complaint pages (Complaints Part 2): access, submission, details and actions."""

import json
import re

from django.test import TestCase
from django.urls import reverse

from complaints import services
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent, ComplaintSubcategory
from complaints.views import PAGE_SIZE

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


class StudentPagesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.categories = make_categories()
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=cls.academics, full_name="Zara Other")
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)])
        cls.admin = make_super_admin()

    def setUp(self):
        self.client.force_login(self.student)

    def detail_url(self, complaint):
        return reverse("student_complaint_detail", args=[complaint.reference])

    def action_url(self, name, complaint):
        return reverse(f"student_complaint_{name}", args=[complaint.reference])

    def submission(self, **overrides):
        data = {
            "category": self.categories["academic"].pk,
            "subcategory": "",
            "title": "Lab timetable clash",
            "description": "Two labs are scheduled at the same time on Tuesdays.",
        }
        data.update(overrides)
        return data


class AccessTests(StudentPagesTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = submit(self.student, self.categories["academic"])
        self.pages = [
            ("get", reverse("student_complaints")),
            ("get", reverse("student_complaint_new")),
            ("get", self.detail_url(self.complaint)),
            ("post", self.action_url("add_information", self.complaint)),
            ("post", self.action_url("still_not_resolved", self.complaint)),
            ("post", self.action_url("request_cancellation", self.complaint)),
        ]

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        self.client.logout()
        for method, url in self.pages:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_staff_cannot_use_student_pages(self):
        for user in (self.advisor, self.admin):
            self.client.force_login(user)
            for method, url in self.pages:
                with self.subTest(user=user.email, url=url):
                    self.assertEqual(getattr(self.client, method)(url, {"message": "x"}).status_code, 403)
        self.assertEqual(self.complaint.events.count(), 1)

    def test_deactivated_student_loses_access(self):
        self.client.force_login(self.student)
        self.student.is_active = False
        self.student.save()
        response = self.client.get(reverse("student_complaints"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_unregistered_student_is_sent_to_registration(self):
        self.client.force_login(make_student("99990000@student.uol.edu.pk"))
        self.assertRedirects(self.client.get(reverse("student_complaint_new")), reverse("student_register"))

    def test_another_students_complaint_is_a_plain_404(self):
        self.client.force_login(self.classmate)
        unknown = reverse("student_complaint_detail", args=["CMP-2026-99999"])
        for url in (self.detail_url(self.complaint), unknown):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, self.complaint.title, status_code=404)
        # Same response for an existing and a non-existent reference: nothing leaks.
        self.assertEqual(self.client.get(self.detail_url(self.complaint)).content, self.client.get(unknown).content)

    def test_another_student_cannot_act_on_the_complaint(self):
        self.client.force_login(self.classmate)
        for name in ("add_information", "still_not_resolved", "request_cancellation"):
            with self.subTest(action=name):
                self.assertEqual(self.client.post(self.action_url(name, self.complaint), {"message": "x"}).status_code, 404)
        self.assertEqual(list(self.complaint.events.values_list("kind", flat=True)), [Kind.SUBMITTED])

    def test_actions_require_post(self):
        for name in ("add_information", "still_not_resolved", "request_cancellation"):
            with self.subTest(action=name):
                self.assertEqual(self.client.get(self.action_url(name, self.complaint)).status_code, 405)


class SubmissionPageTests(StudentPagesTestCase):
    def test_form_lists_active_categories_and_subcategories_only(self):
        ComplaintSubcategory.objects.create(category=self.categories["academic"], name="Retired topic", is_active=False)
        ComplaintCategory.objects.create(name="Old category", is_active=False)
        response = self.client.get(reverse("student_complaint_new"))
        self.assertContains(response, "Test Academic")
        self.assertContains(response, "Academic")  # a seeded row, shown like any other
        self.assertContains(response, '<optgroup label="Test Academic">')
        self.assertContains(response, "Exams")
        self.assertNotContains(response, "Old category")
        self.assertNotContains(response, "Retired topic")
        self.assertNotContains(response, 'name="batch"')
        self.assertNotContains(response, 'name="section"')

    def test_valid_submission_redirects_to_the_new_complaint(self):
        response = self.client.post(reverse("student_complaint_new"), self.submission(subcategory=self.categories["exams"].pk), follow=True)
        complaint = Complaint.objects.get()
        self.assertRedirects(response, self.detail_url(complaint))
        self.assertContains(response, f"Its reference is {complaint.reference}")
        self.assertEqual((complaint.student, complaint.subcategory, complaint.status), (self.student, self.categories["exams"], Status.RECEIVED))

    def test_cohort_comes_from_the_profile_not_the_browser(self):
        a = self.academics
        self.client.post(reverse("student_complaint_new"), self.submission(
            batch=a["other_batch"].pk, semester=a["other_semester"].pk, section=a["other_section"].pk,
            student=self.classmate.pk,
        ))
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.cohort, cohort(a))
        self.assertEqual(complaint.student, self.student)

    def test_inactive_category_is_rejected(self):
        ComplaintCategory.objects.filter(pk=self.categories["other"].pk).update(is_active=False)
        response = self.client.post(reverse("student_complaint_new"), self.submission(category=self.categories["other"].pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose an available category.")
        self.assertFalse(Complaint.objects.exists())

    def test_mismatched_or_unknown_subcategory_is_rejected(self):
        for value, message in (
            (self.categories["exams"].pk, "This subcategory belongs to a different category."),
            (999999, "Choose an available subcategory."),
            ("abc", "Choose an available subcategory."),
        ):
            with self.subTest(value=value):
                response = self.client.post(reverse("student_complaint_new"), self.submission(
                    category=self.categories["other"].pk, subcategory=value,
                ))
                self.assertContains(response, message)
        self.assertFalse(Complaint.objects.exists())

    def test_entirely_empty_post_shows_required_field_errors(self):
        response = self.client.post(reverse("student_complaint_new"), {})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "complaints/student/new.html")
        form = response.context["form"]
        self.assertTrue(form.is_bound)
        self.assertFalse(form.is_valid())
        self.assertEqual(set(form.errors), {"category", "title", "description"})
        for message in ("Choose a category.", "Give your complaint a short title.", "Describe your complaint."):
            self.assertContains(response, message)
        for field in ("category", "title", "description"):
            self.assertContains(response, f'id="id_{field}-error"')
        self.assertFalse(Complaint.objects.exists())
        self.assertFalse(ComplaintEvent.objects.exists())

    def test_invalid_submission_keeps_values_and_marks_errors(self):
        response = self.client.post(reverse("student_complaint_new"), self.submission(title="", description="Still here"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Give your complaint a short title.")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_title-error"')
        self.assertContains(response, "Still here")
        self.assertFalse(Complaint.objects.exists())

    def test_overlong_fields_are_rejected(self):
        response = self.client.post(reverse("student_complaint_new"), self.submission(title="x" * 151, description="y" * 5001))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Complaint.objects.exists())

    def test_duplicate_warning_data_is_own_open_complaints_and_never_blocks(self):
        mine = submit(self.student, self.categories["academic"], title="Earlier clash")
        theirs = submit(self.classmate, self.categories["academic"], title="Classmate private complaint")
        response = self.client.get(reverse("student_complaint_new"))
        data = json.loads(re.search(r'<script id="open-complaints" type="application/json">(.*?)</script>', response.content.decode(), re.S).group(1))
        self.assertEqual([c["reference"] for c in data[str(self.categories["academic"].pk)]], [mine.reference])
        self.assertEqual(data[str(self.categories["other"].pk)], [])
        self.assertNotContains(response, theirs.reference)
        self.assertNotContains(response, "Classmate private complaint")
        # Submitting the same thing again still succeeds (DEC-225).
        self.client.post(reverse("student_complaint_new"), self.submission(title="Earlier clash"))
        self.assertEqual(Complaint.objects.filter(student=self.student).count(), 2)

    def test_students_in_an_inactive_section_see_the_service_message(self):
        self.academics["section"].is_active = False
        self.academics["section"].save()
        response = self.client.post(reverse("student_complaint_new"), self.submission())
        self.assertContains(response, "no longer active")
        self.assertFalse(Complaint.objects.exists())


class ListPageTests(StudentPagesTestCase):
    def test_empty_state(self):
        response = self.client.get(reverse("student_complaints"))
        self.assertContains(response, "You have not submitted any complaints.")
        self.assertContains(response, "Nothing here yet.")
        self.assertContains(response, reverse("student_complaint_new"))

    def test_lists_only_own_complaints(self):
        mine = submit(self.student, self.categories["academic"], title="My complaint")
        submit(self.classmate, self.categories["academic"], title="Classmate complaint")
        response = self.client.get(reverse("student_complaints"))
        self.assertContains(response, mine.reference)
        self.assertContains(response, "My complaint")
        self.assertNotContains(response, "Classmate complaint")
        self.assertContains(response, "You have 1 open complaint.")

    def test_status_filter_and_activity_date(self):
        resolved = submit(self.student, self.categories["academic"], title="Resolved one")
        services.change_status(self.advisor, resolved, Status.RESOLVED, "Fixed.")
        submit(self.student, self.categories["other"], title="Open one")
        response = self.client.get(reverse("student_complaints"), {"status": Status.RESOLVED})
        self.assertContains(response, "Resolved one")
        self.assertNotContains(response, "Open one")
        self.assertContains(response, "Last update")
        self.assertContains(response, f'href="{reverse("student_complaints")}?status=resolved" aria-current="page"')
        # An unknown status shows everything rather than failing.
        response = self.client.get(reverse("student_complaints"), {"status": "overdue"})
        self.assertContains(response, "Resolved one")
        self.assertContains(response, "Open one")

    def test_filter_with_no_matches(self):
        submit(self.student, self.categories["academic"])
        response = self.client.get(reverse("student_complaints"), {"status": Status.REJECTED})
        self.assertContains(response, "No complaints with this status.")

    def test_pagination(self):
        for i in range(PAGE_SIZE + 2):
            submit(self.student, self.categories["academic"], title=f"Complaint number {i}")
        first = self.client.get(reverse("student_complaints"))
        self.assertEqual(len(first.context["page"].object_list), PAGE_SIZE)
        self.assertContains(first, "Page 1 of 2")
        second = self.client.get(reverse("student_complaints"), {"page": 2})
        self.assertEqual(len(second.context["page"].object_list), 2)
        self.assertContains(second, "Complaint number 0")
        self.assertEqual(self.client.get(reverse("student_complaints"), {"page": "x"}).status_code, 200)


class DetailPageTests(StudentPagesTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = submit(self.student, self.categories["academic"], subcategory=self.categories["exams"])

    def get(self):
        return self.client.get(self.detail_url(self.complaint))

    def test_shows_the_case_and_original_description_read_only(self):
        response = self.get()
        self.assertContains(response, self.complaint.reference)
        self.assertContains(response, "Your original complaint")
        self.assertContains(response, self.complaint.description)
        self.assertContains(response, "Test Academic · Exams")
        self.assertContains(response, "Fall 2024 · Semester 4 · Section A")
        self.assertContains(response, "You submitted this complaint")
        self.assertNotContains(response, 'name="description"')

    def test_shows_the_cohort_at_submission_after_the_profile_changes(self):
        profile = self.student.student_profile
        profile.section = self.academics["other_section"]
        profile.save()
        self.assertContains(self.get(), "Fall 2024 · Semester 4 · Section A")

    def test_timeline_shows_responses_and_status_notes_by_role_only(self):
        services.respond(self.advisor, self.complaint, "Which lab sessions?")
        services.change_status(self.advisor, self.complaint, Status.REJECTED, "Not a departmental matter.")
        services.assign_responsible(self.admin, self.complaint, self.advisor)
        response = self.get()
        self.assertContains(response, "Response from Batch Advisor")
        self.assertContains(response, "Which lab sessions?")
        self.assertContains(response, "Status changed to Rejected")
        self.assertContains(response, "Reason for rejection")
        self.assertContains(response, "Not a departmental matter.")
        # No staff names or emails, no internal owner changes, no raw values.
        self.assertNotContains(response, self.advisor.full_name)
        self.assertNotContains(response, self.advisor.email)
        self.assertNotContains(response, "Responsible")
        self.assertNotContains(response, "responsible_changed")
        self.assertNotContains(response, "status_changed")
        titles = [entry.title for entry in response.context["timeline"]]
        self.assertEqual(titles, ["You submitted this complaint", "Response from Batch Advisor", "Status changed to Rejected"])

    def test_add_further_information(self):
        original = self.complaint.description
        response = self.client.post(self.action_url("add_information", self.complaint), {"message": "Tuesday, labs 2 and 4."}, follow=True)
        self.assertRedirects(response, self.detail_url(self.complaint))
        self.assertContains(response, "Your information was added")
        self.assertContains(response, "You added further information")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.description, original)
        self.assertEqual(list(self.complaint.events.values_list("kind", flat=True)), [Kind.SUBMITTED, Kind.FURTHER_INFORMATION])

    def test_empty_further_information_is_rejected_with_a_useful_error(self):
        response = self.client.post(self.action_url("add_information", self.complaint), {"message": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Write the information you want to add.", status_code=400)
        self.assertContains(response, "<details class=\"sa-action\" open>", status_code=400)
        self.assertEqual(self.complaint.events.count(), 1)

    def test_still_not_resolved_only_for_resolved_complaints(self):
        self.assertNotContains(self.get(), "Mark as still not resolved")
        # Posting anyway is refused by the service, explained on the page, and nothing changes.
        response = self.client.post(self.action_url("still_not_resolved", self.complaint), {"message": ""}, follow=True)
        self.assertRedirects(response, self.detail_url(self.complaint))
        self.assertContains(response, "Only a resolved complaint can be marked as still not resolved.")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.RECEIVED)

        services.change_status(self.advisor, self.complaint, Status.RESOLVED, "Timetable fixed.")
        self.assertContains(self.get(), "Mark as still not resolved")
        response = self.client.post(self.action_url("still_not_resolved", self.complaint), {"message": "Still clashing."}, follow=True)
        self.assertContains(response, "back Under Review")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.UNDER_REVIEW)
        self.assertContains(response, "You said this is still not resolved")

    def test_cancellation_request_records_without_changing_status(self):
        response = self.get()
        self.assertContains(response, "It does not cancel or delete the complaint.")
        response = self.client.post(self.action_url("request_cancellation", self.complaint), {"reason": "Sorted out."}, follow=True)
        self.assertContains(response, "Your cancellation request was recorded.")
        self.assertContains(response, "You asked to cancel this complaint")
        self.assertContains(response, "Sorted out.")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Status.RECEIVED)
        self.assertTrue(Complaint.objects.filter(pk=self.complaint.pk).exists())
        # The form is replaced by a note once a request is recorded.
        self.assertNotContains(response, "Send cancellation request")
        self.assertContains(response, "You have asked to cancel this complaint.")

    def test_no_delete_or_status_controls_for_students(self):
        content = self.get().content.decode()
        self.assertNotRegex(content, r'name="status"')
        self.assertNotIn("Delete", content)


class NavigationIntegrationTests(StudentPagesTestCase):
    def test_complaints_navigation_and_quick_access_link_to_the_pages(self):
        home = self.client.get(reverse("student_home")).content.decode()
        self.assertIn(f'href="{reverse("student_complaint_new")}"', home)
        self.assertRegex(home, r'<a class="sa-nav-link" href="{}"'.format(re.escape(reverse("student_complaints"))))

    def test_complaints_stays_current_on_its_sub_pages(self):
        complaint = submit(self.student, self.categories["academic"])
        for url in (reverse("student_complaints"), reverse("student_complaint_new"), self.detail_url(complaint)):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertRegex(html, r'<a class="sa-nav-link" href="{}" aria-current="page">'.format(re.escape(reverse("student_complaints"))))
