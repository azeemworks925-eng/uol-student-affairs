"""Super Admin Overview analytics (Complaints Part 4 Stage 4b; COMPLAINTS_PART4_SPEC.md section 6).

Small-cohort suppression was removed by DEC-339 (amending DEC-315, DEC-318 and DEC-319): every
real cohort shows its count, and there is no withheld state.
"""

import re
from datetime import date, datetime, timedelta
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from academics import services as term_services
from academics.models import REPORTING_TIME_ZONE, AcademicTerm, Batch, Section
from complaints import analytics
from complaints.analytics import build_overview, percent
from complaints.models import Complaint, ComplaintCategory
from complaints.workspace import cohort_value

from .helpers import make_academics, make_advisor, make_student, make_super_admin

Status = Complaint.Status
OVERVIEW = reverse("super_admin_home")
LIST = reverse("super_admin_complaints")
KHI = REPORTING_TIME_ZONE
IN_TERM = datetime(2026, 10, 15, 12, tzinfo=KHI)


class PercentTests(SimpleTestCase):
    def test_rounding_and_zero_total(self):
        self.assertEqual(percent(1, 3), 33)
        self.assertEqual(percent(1, 8), 13)  # 12.5 rounds half up
        self.assertIsNone(percent(0, 0))
        self.assertEqual(analytics.percent_label(1, 400), "<1%")
        self.assertEqual(analytics.percent_label(0, 4), "0%")


# ---------------------------------------------------------------------------------------------
# The Overview with real data
# ---------------------------------------------------------------------------------------------

_next_sap = iter(range(30000000, 39999999))


def make_students(cohort, count, *, inactive=0):
    """`count` registered students in the exact cohort, the first `inactive` of them deactivated."""
    batch, semester, section = cohort
    students = []
    for i in range(count):
        student = make_student(f"{next(_next_sap)}@student.uol.edu.pk", academics={"batch": batch},
                               cohort=cohort, full_name=f"Student {i}")
        if i < inactive:
            student.is_active = False
            student.save()
        students.append(student)
    return students


def add_complaints(student, cohort, category, count, *, status=Status.RECEIVED, at=IN_TERM):
    """Insert complaints directly (fixtures need many, at chosen times and statuses)."""
    batch, semester, section = cohort
    with mock.patch("django.utils.timezone.now", return_value=at):
        Complaint.objects.bulk_create([
            Complaint(student=student, batch=batch, semester=semester, section=section, category=category,
                      title="Analytics fixture", description="Fixture.", status=status)
            for _ in range(count)
        ])


def make_term(name="Fall 2026", start=date(2026, 9, 1), end=date(2027, 1, 15), current=True):
    term = AcademicTerm.objects.create(name=name, start_date=start, end_date=end)
    if current:
        term_services.set_current_term(term)
    return term


class OverviewTestCase(TestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    @classmethod
    def setUpTestData(cls):
        cls.a = make_academics()
        cls.admin = make_super_admin()
        cls.cat_main = ComplaintCategory.objects.create(name="Analytics Main", position=1)
        cls.cat_other = ComplaintCategory.objects.create(name="Analytics Other", position=2)

    def overview(self):
        response = self.client.get(OVERVIEW)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # The whole page content. Today's date line is not data, so its digits are left out.
        region = html[html.index('<main'):html.index('</main>')]
        region = re.sub(r'<p class="sa-hero-date">.*?</p>', "", region)
        return response.context["analytics"], region

    def cohort(self, batch="batch", semester="semester", section="section"):
        return self.a[batch], self.a[semester], self.a[section]


class SetupStateTests(OverviewTestCase):
    def test_no_current_term_shows_the_setup_state_and_no_figures(self):
        students = make_students(self.cohort(), 6)
        add_complaints(students[0], self.cohort(), self.cat_main, 7)
        make_term(current=False)  # a term exists, but none is current
        overview, region = self.overview()
        self.assertEqual(overview.state, "setup")
        self.assertIn("Set the current academic term", region)
        self.assertIn(reverse("super_admin_terms"), region)
        self.assertNotIn(LIST, region)
        self.assertNotIn("sa-stat", region)
        self.assertIsNone(re.search(r"\b7\b", region))  # never an all-time fallback


class WindowAndAggregationTests(OverviewTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.term = make_term()
        cohort_a = (cls.a["batch"], cls.a["semester"], cls.a["section"])
        cohort_b = (cls.a["other_batch"], cls.a["semester"], cls.a["section"])
        cls.students_a, cls.students_b = make_students(cohort_a, 6), make_students(cohort_b, 5)
        start, after_end = datetime(2026, 9, 1, tzinfo=KHI), datetime(2027, 1, 16, tzinfo=KHI)
        s = cls.students_a[0]
        add_complaints(s, cohort_a, cls.cat_main, 1, at=start)  # exactly at the start: in
        add_complaints(s, cohort_a, cls.cat_main, 1, at=start - timedelta(microseconds=1))  # out
        add_complaints(s, cohort_a, cls.cat_main, 1, at=after_end - timedelta(microseconds=1), status=Status.RESOLVED)  # in
        add_complaints(s, cohort_a, cls.cat_main, 1, at=after_end)  # out
        add_complaints(cls.students_b[0], cohort_b, cls.cat_other, 2, status=Status.UNDER_REVIEW)
        add_complaints(cls.students_b[0], cohort_b, cls.cat_main, 1, status=Status.REJECTED)
        cls.retired = ComplaintCategory.objects.create(name="Analytics Retired", position=3, is_active=False)
        cls.unused_retired = ComplaintCategory.objects.create(name="Analytics Unused Retired", position=4, is_active=False)
        add_complaints(cls.students_b[0], cohort_b, cls.retired, 1, status=Status.RESOLVED)

    def test_window_boundaries_and_totals(self):
        overview, region = self.overview()
        self.assertEqual(overview.state, "ready")
        self.assertEqual(overview.total, 6)
        self.assertIn("6 complaints in Fall 2026.", region)
        self.assertIn("1 Sep 2026 – 15 Jan 2027", region)
        cells = {c.label: c.count for c in overview.cohorts}
        self.assertEqual(cells, {"Fall 2024 · Semester 4 · Section A": 2, "Spring 2025 · Semester 4 · Section A": 4})

    def test_categories_follow_dec_321_and_reconcile(self):
        overview, region = self.overview()
        shares = {c.label: (c.count, c.percent, c.inactive) for c in overview.categories}
        self.assertEqual(shares["Analytics Main"], (3, 50, False))
        self.assertEqual(shares["Analytics Other"], (2, 33, False))
        self.assertEqual(shares["Analytics Retired"], (1, 17, True))
        self.assertNotIn("Analytics Unused Retired", shares)
        for seeded in ComplaintCategory.objects.filter(is_active=True):
            self.assertIn(seeded.name, shares)  # active categories with zero complaints are listed
        self.assertEqual(sum(c.count for c in overview.categories), overview.total)
        self.assertIn("Analytics Retired <span class=\"sa-muted\">(inactive)</span>", region)

    def test_resolved_versus_not_resolved(self):
        overview, region = self.overview()
        self.assertEqual((overview.resolved.count, overview.not_resolved.count), (2, 4))
        self.assertEqual([(p.label, p.count) for p in overview.not_resolved_parts],
                         [("Received", 1), ("Under review", 2), ("Rejected", 1)])
        self.assertEqual(overview.resolved.count + overview.not_resolved.count, overview.total)
        self.assertEqual(overview.status_takeaway, "2 of 6 resolved (33%).")
        # Rejected complaints are never described as awaiting action (DEC-313).
        self.assertNotIn("awaiting", region.lower())

    def test_another_term_is_not_counted(self):
        make_term("Spring 2027", date(2027, 2, 1), date(2027, 6, 30))
        overview, _ = self.overview()
        self.assertEqual(overview.total, 0)

    def test_visible_links_drill_down_with_the_term(self):
        overview, region = self.overview()
        cohort_b = (self.a["other_batch"].pk, self.a["semester"].pk, self.a["section"].pk)
        cell = next(c for c in overview.cohorts if c.label.startswith("Spring 2025"))
        self.assertEqual(cell.url, f"{LIST}?cohort={cohort_value(*cohort_b)}&term={self.term.pk}")
        response = self.client.get(cell.url)
        self.assertEqual(response.context["page"].paginator.count, cell.count)
        category = next(c for c in overview.categories if c.label == "Analytics Other")
        self.assertEqual(self.client.get(category.url).context["page"].paginator.count, 2)
        self.assertEqual(self.client.get(overview.resolved.url).context["page"].paginator.count, 2)
        for part in overview.not_resolved_parts:
            self.assertEqual(self.client.get(part.url).context["page"].paginator.count, part.count)
        self.assertIn(cell.url.replace("&", "&amp;"), region)

    def test_queries_do_not_grow_with_cohorts(self):
        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                build_overview(self.admin)
            return len(queries)

        before = count_queries()
        for name in ("C", "D", "E"):
            section = Section.objects.create(name=name)
            make_students((self.a["batch"], self.a["semester"], section), 5)
        self.assertEqual(count_queries(), before)


class CohortUniverseTests(OverviewTestCase):
    def test_every_real_cohort_in_academic_order_with_short_labels(self):
        make_term()
        big = make_students(self.cohort(), 6)
        make_students(self.cohort(semester="other_semester", section="other_section"), 7)
        add_complaints(big[0], self.cohort(), self.cat_main, 3)
        overview, region = self.overview()
        self.assertEqual([(c.short_label, c.count) for c in overview.cohorts], [("A · S4", 3), ("B · S5", 0)])
        self.assertEqual(overview.cohorts[0].label, "Fall 2024 · Semester 4 · Section A")
        self.assertIn('title="Fall 2024 · Semester 4 · Section A"', region)  # the full cohort on hover

    def test_assignment_and_complaint_cohorts_are_real_and_inactive_entries_are_kept(self):
        make_term()
        inactive_batch = Batch.objects.create(name="Fall 2019", is_active=False)
        students = make_students(self.cohort(), 8)
        make_advisor(cohorts=[self.cohort(batch="other_batch")])  # no students, still a real cohort
        add_complaints(students[0], (inactive_batch, self.a["semester"], self.a["section"]), self.cat_main, 2)
        add_complaints(students[0], self.cohort(), self.cat_main, 4)
        overview, _ = self.overview()
        counts = {c.label: c.count for c in overview.cohorts}
        self.assertEqual(counts["Fall 2019 · Semester 4 · Section A"], 2)
        self.assertEqual(counts["Spring 2025 · Semester 4 · Section A"], 0)
        self.assertEqual(counts["Fall 2024 · Semester 4 · Section A"], 4)


class NoSuppressionTests(OverviewTestCase):
    """DEC-339: small cohorts show their real counts; there is no hidden or withheld state."""

    def test_a_small_cohort_shows_its_count(self):
        make_term()
        small = make_students(self.cohort(), 2)
        make_students(self.cohort(batch="other_batch"), 9)
        add_complaints(small[0], self.cohort(), self.cat_main, 3)
        overview, region = self.overview()
        self.assertEqual(overview.state, "ready")
        self.assertEqual({c.label: c.count for c in overview.cohorts}["Fall 2024 · Semester 4 · Section A"], 3)
        self.assertIn(f"cohort={cohort_value(*(p.pk for p in self.cohort()))}", region)
        for gone in ("Hidden for privacy", "withheld", "fewer than five", "sa-map", "sa-cell"):
            self.assertNotIn(gone, region)

    def test_zero_total_with_a_small_cohort_is_ready(self):
        make_term()
        make_students(self.cohort(), 3)
        overview, region = self.overview()
        self.assertEqual((overview.state, overview.total), ("ready", 0))
        self.assertIn("No complaints in Fall 2026 yet.", region)

    def test_the_only_real_cohort_can_be_small(self):
        make_term()
        small = make_students(self.cohort(), 1)
        add_complaints(small[0], self.cohort(), self.cat_main, 3)
        overview, _ = self.overview()
        self.assertEqual((overview.state, overview.total), ("ready", 3))

    def test_the_suppression_code_is_gone(self):
        for name in ("MIN_ACTIVE_STUDENTS", "plan_suppression", "determined_keys", "CohortCell"):
            self.assertFalse(hasattr(analytics, name), name)
        self.assertNotIn("hidden_cells", analytics.Overview.__dataclass_fields__)


class EmptyTermTests(OverviewTestCase):
    def test_no_complaints_and_no_small_cohorts(self):
        make_term()
        make_students(self.cohort(), 5)
        overview, region = self.overview()
        self.assertEqual((overview.state, overview.total), ("ready", 0))
        self.assertIn("No complaints in Fall 2026 yet.", region)
        self.assertEqual(overview.resolved.percent_label, "")
        self.assertIn("No complaints this term", region)
        self.assertNotIn("sa-donut-arc", region)


class AccessTests(OverviewTestCase):
    def test_only_active_super_admins(self):
        make_term()
        self.client.logout()
        response = self.client.get(OVERVIEW)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))
        student = make_students(self.cohort(), 1)[0]
        advisor = make_advisor(cohorts=[self.cohort()])
        for user in (student, advisor):
            self.client.force_login(user)
            with self.subTest(user=user.email):
                self.assertEqual(self.client.get(OVERVIEW).status_code, 403)
        self.admin.is_active = False
        self.admin.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(OVERVIEW).status_code, 302)

    def test_complaint_list_access_for_a_small_cohort(self):
        # DEC-320: the complaint list keeps its cohort and term filters.
        make_term()
        small = make_students(self.cohort(), 3)
        make_students(self.cohort(batch="other_batch"), 9)
        add_complaints(small[0], self.cohort(), self.cat_main, 2)
        term = AcademicTerm.objects.get()
        url = f"{LIST}?cohort={cohort_value(*(p.pk for p in self.cohort()))}&term={term.pk}"
        self.assertEqual(self.client.get(url).context["page"].paginator.count, 2)
