"""The Super Admin complaint list's academic-term filter (Complaints Part 4 Stage 4a).

Complaints are counted by submission date within the term's reporting window: the start date
00:00 Asia/Karachi (inclusive) to the day after the end date 00:00 (exclusive). The filter only
narrows the Super Admin's list; the Batch Advisor list and student pages ignore `term`.
"""

from datetime import date, datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from academics import services as term_services
from academics.models import REPORTING_TIME_ZONE, AcademicTerm
from complaints import services
from complaints.models import Complaint
from complaints.workspace import cohort_value

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
LIST = reverse("super_admin_complaints")
ADVISOR_LIST = reverse("advisor_complaints")
STUDENT_LIST = reverse("student_complaints")
KHI = REPORTING_TIME_ZONE


def submit_at(moment, student, category, **overrides):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        return submit(student, category, **overrides)


def query(url):
    return parse_qs(urlparse(url).query)


class TermFilterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        cls.categories = make_categories()
        cls.home = cohort(a)
        cls.other = cohort(a, batch="other_batch")
        cls.student = make_student(academics=a, full_name="Ali Khan")
        cls.other_student = make_student(OTHER_STUDENT_EMAIL, academics=a, cohort=cls.other, full_name="Zara Ahmed")
        cls.admin = make_super_admin()
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")

        cls.fall = AcademicTerm.objects.create(name="Fall 2026", start_date=date(2026, 9, 1), end_date=date(2027, 1, 15))
        cls.spring = AcademicTerm.objects.create(name="Spring 2026", start_date=date(2026, 2, 1), end_date=date(2026, 6, 30))
        term_services.set_current_term(cls.fall)

        academic, other = cls.categories["academic"], cls.categories["other"]
        start = datetime(2026, 9, 1, tzinfo=KHI)
        after_end = datetime(2027, 1, 16, tzinfo=KHI)
        # Exactly on the boundaries of Fall 2026.
        cls.at_start = submit_at(start, cls.student, academic, title="At the start")
        cls.just_before = submit_at(start - timedelta(microseconds=1), cls.student, academic, title="Just before")
        cls.late_on_end = submit_at(after_end - timedelta(microseconds=1), cls.other_student, other, title="Late on the last day")
        cls.at_midnight_after = submit_at(after_end, cls.other_student, other, title="Midnight after")
        cls.in_spring = submit_at(datetime(2026, 3, 10, 12, tzinfo=KHI), cls.student, academic, title="Spring visit")
        cls.mid_fall = submit_at(datetime(2026, 11, 5, 9, tzinfo=KHI), cls.other_student, academic, title="Mid fall")

    def setUp(self):
        self.client.force_login(self.admin)

    def refs(self, response):
        return {c.reference for c in response.context["page"].object_list}

    def get(self, **params):
        return self.client.get(LIST, params)


class TermOnlyTests(TermFilterTestCase):
    def test_without_a_term_every_complaint_is_listed(self):
        self.assertEqual(len(self.refs(self.get())), 6)

    def test_term_uses_the_inclusive_start_and_exclusive_end(self):
        response = self.get(term=self.fall.pk)
        self.assertEqual(
            self.refs(response), {self.at_start.reference, self.late_on_end.reference, self.mid_fall.reference}
        )

    def test_another_term(self):
        self.assertEqual(self.refs(self.get(term=self.spring.pk)), {self.in_spring.reference})

    def test_the_window_is_stored_in_utc_and_compared_correctly(self):
        # 00:00 on 1 Sep in Karachi is 19:00 UTC on 31 Aug.
        stored = Complaint.objects.filter(pk=self.at_start.pk).values_list("created_at", flat=True).get()
        self.assertEqual((stored.utcoffset(), stored.hour, stored.day), (timedelta(0), 19, 31))

    def test_a_term_with_no_complaints_shows_the_filtered_empty_state(self):
        empty = AcademicTerm.objects.create(name="Summer 2026", start_date=date(2026, 7, 1), end_date=date(2026, 8, 15))
        response = self.get(term=empty.pk)
        self.assertEqual(self.refs(response), set())
        self.assertContains(response, "No complaints match these filters.")

    def test_the_widest_supported_term_filters_without_error(self):
        # Dates outside 1900-9998 cannot be stored (academics.0003), so every stored term has a
        # window that converts to UTC; the extremes that can exist are handled.
        widest = AcademicTerm.objects.create(name="Widest", start_date=date(1900, 1, 1), end_date=date(9998, 12, 31))
        response = self.get(term=widest.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.refs(response)), 6)

    def test_invalid_or_unknown_terms_are_ignored(self):
        for value in ("abc", "999999", "-1", "1.5", " ", "%00", str(self.fall.pk) + "x"):
            with self.subTest(value=value):
                response = self.get(term=value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(self.refs(response)), 6)
                self.assertIsNone(response.context["selected_term"])
                self.assertNotContains(response, "sa-filter-chip")
                self.assertFalse(response.context["has_filters"])


class CombinedFilterTests(TermFilterTestCase):
    def test_term_and_cohort(self):
        a = self.academics
        home = cohort_value(a["batch"].pk, a["semester"].pk, a["section"].pk)
        other = cohort_value(a["other_batch"].pk, a["semester"].pk, a["section"].pk)
        self.assertEqual(self.refs(self.get(term=self.fall.pk, cohort=home)), {self.at_start.reference})
        self.assertEqual(
            self.refs(self.get(term=self.fall.pk, cohort=other)), {self.late_on_end.reference, self.mid_fall.reference}
        )

    def test_term_and_category(self):
        response = self.get(term=self.fall.pk, category=self.categories["other"].pk)
        self.assertEqual(self.refs(response), {self.late_on_end.reference})

    def test_term_and_status(self):
        services.change_status(self.admin, self.mid_fall, Status.UNDER_REVIEW)
        services.change_status(self.admin, self.in_spring, Status.UNDER_REVIEW)
        self.assertEqual(self.refs(self.get(term=self.fall.pk, status=Status.UNDER_REVIEW)), {self.mid_fall.reference})
        self.assertEqual(
            self.refs(self.get(term=self.fall.pk, status=Status.RECEIVED)),
            {self.at_start.reference, self.late_on_end.reference},
        )

    def test_term_with_owner_and_search(self):
        services.assign_responsible(self.admin, self.at_start, self.advisor)
        services.assign_responsible(self.admin, self.just_before, self.advisor)
        response = self.get(term=self.fall.pk, owner=self.advisor.pk)
        self.assertEqual(self.refs(response), {self.at_start.reference})
        response = self.get(term=self.fall.pk, owner="unassigned")
        self.assertEqual(self.refs(response), {self.late_on_end.reference, self.mid_fall.reference})
        self.assertEqual(self.refs(self.get(term=self.fall.pk, q="Zara")), {self.late_on_end.reference, self.mid_fall.reference})
        self.assertEqual(self.refs(self.get(term=self.fall.pk, q="Just before")), set())


class ChipAndStateTests(TermFilterTestCase):
    def test_term_choices_name_the_dates_and_the_current_term(self):
        choices = dict(self.get().context["filters"].fields["term"].choices)
        self.assertEqual(choices[""], "Any term")
        self.assertEqual(choices[str(self.fall.pk)], "Fall 2026 (1 Sep 2026 – 15 Jan 2027), current")
        self.assertEqual(choices[str(self.spring.pk)], "Spring 2026 (1 Feb 2026 – 30 Jun 2026)")

    def test_chip_shows_the_term_name_and_exact_dates(self):
        response = self.get(term=self.fall.pk)
        html = response.content.decode()
        chip = html[html.index('class="sa-filter-chip"'):html.index("</p>", html.index('class="sa-filter-chip"'))]
        self.assertIn("Fall 2026", chip)
        self.assertIn("1 Sep 2026 – 15 Jan 2027", chip)
        self.assertIn('aria-label="Remove the academic term filter (Fall 2026)"', chip)
        self.assertTrue(response.context["has_filters"])
        self.assertContains(response, "Clear filters")

    def test_removing_the_term_keeps_the_other_filters(self):
        response = self.get(term=self.fall.pk, status=Status.RECEIVED, q="Ali", sort="newest", page="2")
        remove = response.context["term_clear_url"]
        self.assertTrue(remove.startswith(LIST))
        self.assertEqual(query(remove), {"status": [Status.RECEIVED], "q": ["Ali"], "sort": ["newest"]})
        self.assertContains(response, f'href="{remove.replace("&", "&amp;")}"')
        self.assertEqual(self.get(term=self.fall.pk).context["term_clear_url"], LIST)

    def test_clear_filters_removes_the_term_too(self):
        response = self.get(term=self.fall.pk, status=Status.RECEIVED)
        self.assertContains(response, f'<a class="btn btn-sa-secondary btn-sm" href="{LIST}">Clear filters</a>', html=True)

    def test_pagination_and_case_links_keep_the_term(self):
        with mock.patch("complaints.workspace.PAGE_SIZE", 1):
            response = self.get(term=self.fall.pk, sort="newest")
        page = response.context["page"]
        self.assertEqual((page.paginator.count, page.paginator.num_pages), (3, 3))
        self.assertIn(f"term={self.fall.pk}", response.context["list_state_without_page"])
        self.assertContains(response, f"term={self.fall.pk}&amp;sort=newest&amp;page=2")
        state = response.context["list_state"]
        self.assertEqual(query(f"?{state}")["term"], [str(self.fall.pk)])

        detail = reverse("super_admin_complaint_detail", args=[self.mid_fall.reference])
        response = self.client.get(detail, {"term": self.fall.pk})
        self.assertEqual(self.refs(response), {self.at_start.reference, self.late_on_end.reference, self.mid_fall.reference})
        self.assertContains(response, f"?term={self.fall.pk}")

    def test_actions_redirect_back_with_the_term(self):
        url = reverse("super_admin_complaint_respond", args=[self.mid_fall.reference]) + f"?term={self.fall.pk}"
        response = self.client.post(url, {"message": "We are looking into it."})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(query(response["Location"]), {"term": [str(self.fall.pk)]})


class AccessTests(TermFilterTestCase):
    def test_access_rules_are_unchanged(self):
        self.client.logout()
        response = self.get(term=self.fall.pk)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))
        for user in (self.student, self.advisor):
            self.client.force_login(user)
            with self.subTest(user=user.email):
                self.assertEqual(self.get(term=self.fall.pk).status_code, 403)
        self.admin.is_active = False
        self.admin.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.get(term=self.fall.pk).status_code, 302)


class BatchAdvisorListTests(TermFilterTestCase):
    """The Batch Advisor list has no term filter and ignores a forged `term` parameter."""

    def setUp(self):
        self.client.force_login(self.advisor)

    def test_term_is_ignored_and_not_offered(self):
        plain = self.client.get(ADVISOR_LIST)
        forged = self.client.get(ADVISOR_LIST, {"term": self.fall.pk})
        mine = {self.at_start.reference, self.just_before.reference, self.in_spring.reference}
        self.assertEqual(self.refs(plain), mine)
        self.assertEqual(self.refs(forged), mine)
        self.assertNotIn("term", forged.context["filters"].fields)
        self.assertNotContains(forged, "Academic term")
        self.assertNotContains(forged, "sa-filter-chip")
        self.assertFalse(forged.context["has_filters"])

    def test_term_is_not_carried_in_advisor_links(self):
        response = self.client.get(ADVISOR_LIST, {"term": self.fall.pk, "status": Status.RECEIVED})
        self.assertEqual(response.context["list_state"], f"status={Status.RECEIVED}")
        self.assertNotContains(response, "term=")
        url = reverse("advisor_complaint_respond", args=[self.at_start.reference]) + f"?term={self.fall.pk}&status=received"
        response = self.client.post(url, {"message": "Noted."})
        self.assertEqual(query(response["Location"]), {"status": ["received"]})

    def test_queries_are_unchanged_by_a_term_parameter(self):
        def sql(params):
            with CaptureQueriesContext(connection) as captured:
                self.client.get(ADVISOR_LIST, params)
            return [q["sql"] for q in captured.captured_queries if "django_session" not in q["sql"]]

        plain, forged = sql({}), sql({"term": self.fall.pk})
        self.assertEqual(forged, plain)
        self.assertFalse(any("academics_academicterm" in statement for statement in forged))


class StudentPageTests(TermFilterTestCase):
    def test_student_list_ignores_a_term_parameter(self):
        self.client.force_login(self.student)
        plain = self.client.get(STUDENT_LIST)
        forged = self.client.get(STUDENT_LIST, {"term": self.fall.pk})
        self.assertEqual(forged.status_code, 200)
        self.assertEqual(self.refs(forged), self.refs(plain))
        self.assertEqual(self.refs(forged), {self.at_start.reference, self.just_before.reference, self.in_spring.reference})
        self.assertNotContains(forged, "Academic term")
        self.assertNotContains(forged, "sa-filter-chip")
