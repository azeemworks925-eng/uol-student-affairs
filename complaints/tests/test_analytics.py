"""Super Admin Overview analytics (Complaints Part 4 Stage 4b; COMPLAINTS_PART4_SPEC.md section 6).

Privacy is tested at two levels: the pure suppression functions against an independent
brute-force uniqueness check (spec 6.4 and section 8), and the rendered Overview, whose HTML,
context and links must never carry a suppressed value.
"""

import dataclasses
import random
import re
from datetime import date, datetime, timedelta
from itertools import combinations, product
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from academics import services as term_services
from academics.models import REPORTING_TIME_ZONE, AcademicTerm, Batch, Section, Semester
from accounts.models import AdvisorAssignment
from complaints import analytics
from complaints.analytics import MIN_ACTIVE_STUDENTS, build_overview, determined_keys, percent, plan_suppression
from complaints.models import Complaint, ComplaintCategory
from complaints.workspace import cohort_value

from .helpers import make_academics, make_advisor, make_student, make_super_admin

Status = Complaint.Status
OVERVIEW = reverse("super_admin_home")
LIST = reverse("super_admin_complaints")
KHI = REPORTING_TIME_ZONE
IN_TERM = datetime(2026, 10, 15, 12, tzinfo=KHI)


# ---------------------------------------------------------------------------------------------
# An independent check: which hidden values does the page determine uniquely?
# ---------------------------------------------------------------------------------------------

def brute_force_determined(hidden_counts, total, visible_counts, lower_bounds=None):
    """Enumerate every assignment of the hidden cells consistent with what the page shows: the
    visible cells, the total T (which the category and status chapters reveal), and each cell's
    known lower bound (0, or 1 for a cohort that appears only because of its complaints)."""
    lower = lower_bounds or {}
    keys = sorted(hidden_counts)
    remainder = total - sum(visible_counts.values())
    seen = {k: set() for k in keys}
    for values in product(range(remainder + 1), repeat=len(keys)):
        if sum(values) == remainder and all(v >= lower.get(k, 0) for k, v in zip(keys, values)):
            for k, v in zip(keys, values):
                seen[k].add(v)
    return {k for k in keys if len(seen[k]) <= 1}


def safe_arrangement_exists(cells, lower_bounds=None):
    primary = {k for k, (_, s) in cells.items() if s < MIN_ACTIVE_STUDENTS}
    total = sum(n for n, _ in cells.values())
    others = [k for k in cells if k not in primary]
    for size in range(len(others) + 1):
        for extra in combinations(others, size):
            hidden = primary | set(extra)
            visible = {k: cells[k][0] for k in cells if k not in hidden}
            if not brute_force_determined({k: cells[k][0] for k in hidden}, total, visible, lower_bounds):
                return True
    return False


class SuppressionExamplesTests(SimpleTestCase):
    """The worked examples of spec 6.4 and the deterministic cases of section 8."""

    def plan(self, cells, lower_bounds=None):
        order = sorted(cells, key=lambda k: (-cells[k][1], k))
        return plan_suppression(cells, order, lower_bounds)

    def assert_safe(self, cells, hidden, lower_bounds=None):
        total = sum(n for n, _ in cells.values())
        visible = {k: cells[k][0] for k in cells if k not in hidden}
        self.assertEqual(
            brute_force_determined({k: cells[k][0] for k in hidden}, total, visible, lower_bounds), set()
        )

    def test_a_cohort_known_to_have_complaints_is_not_pinned_by_its_lower_bound(self):
        # Review regression: X appears only because of its complaints, so X >= 1. Pairing X (1)
        # with a zero-complaint complement would show X + Y = 1, forcing X = 1 and Y = 0.
        lower = {"X": 1}
        self.assertEqual(brute_force_determined({"X": 1, "Y": 0}, 6, {"Z": 5}, lower), {"X", "Y"})
        self.assertEqual(determined_keys({"X": 1, "Y": 0}, [{"X", "Y"}], lower), {"X", "Y"})
        cells = {"X": (1, 0), "Y": (0, 40), "Z": (5, 30)}
        hidden = self.plan(cells, lower)
        self.assertEqual(hidden, frozenset({"X", "Z"}))
        self.assert_safe(cells, hidden, lower)

    def test_lower_bounds_in_overlapping_equations(self):
        lower = {"A": 1, "B": 1}
        self.assertEqual(determined_keys({"A": 1, "B": 1, "C": 0}, [{"A", "B", "C"}, {"A", "C"}], lower), {"A", "B", "C"})
        self.assertEqual(determined_keys({"A": 2, "B": 1, "C": 1}, [{"A", "B", "C"}, {"A", "C"}], lower), {"B"})

    def test_no_safe_arrangement_when_every_cell_sits_at_its_lower_bound(self):
        # Two complaint-only cohorts with one complaint each, and nothing else with complaints.
        lower = {"X": 1, "W": 1}
        self.assertIsNone(self.plan({"X": (1, 0), "W": (1, 9), "Y": (0, 40)}, lower))

    def test_no_small_cohort_hides_nothing(self):
        self.assertEqual(self.plan({"A": (2, 9), "B": (3, 5)}), frozenset())

    def test_one_small_cohort_is_never_hidden_alone(self):
        # A* = 2, B = 3, C = 4: hiding A alone would let T = 9 reveal A = 9 - 3 - 4.
        cells = {"A": (2, 3), "B": (3, 20), "C": (4, 30)}
        self.assertEqual(brute_force_determined({"A": 2}, 9, {"B": 3, "C": 4}), {"A"})
        hidden = self.plan(cells)
        self.assertIn("A", hidden)
        self.assertGreaterEqual(len(hidden), 2)
        self.assert_safe(cells, hidden)

    def test_two_hidden_cohorts_with_a_non_zero_total_are_safe(self):
        # A* = 2, B* = 3, C = 4: only A + B = 5 is known; six pairs fit.
        self.assertEqual(brute_force_determined({"A": 2, "B": 3}, 9, {"C": 4}), set())
        cells = {"A": (2, 3), "B": (3, 4), "C": (4, 30)}  # both small: no complement needed
        self.assertEqual(self.plan(cells), frozenset({"A", "B"}))

    def test_hidden_cohorts_adding_up_to_zero_are_rejected(self):
        # A* = 0 with B preferred as complement but B = 0: A + B = 0 would force both to 0.
        self.assertEqual(brute_force_determined({"A": 0, "B": 0}, 4, {"C": 4}), {"A", "B"})
        self.assertEqual(determined_keys({"A": 0, "B": 0}, [{"A", "B"}]), {"A", "B"})
        cells = {"A": (0, 3), "B": (0, 40), "C": (4, 30)}
        hidden = self.plan(cells)
        self.assertEqual(hidden, frozenset({"A", "C"}))  # B stays visible as zero
        self.assert_safe(cells, hidden)

    def test_two_small_cohorts_adding_up_to_zero_get_a_complement(self):
        cells = {"A": (0, 3), "B": (0, 2), "C": (5, 30), "D": (1, 9)}
        hidden = self.plan(cells)
        self.assertTrue({"A", "B"} < hidden)
        self.assert_safe(cells, hidden)

    def test_a_value_made_unique_by_another_displayed_equation_is_rejected(self):
        # If a subtotal containing only A were also displayed, A would be determined.
        self.assertEqual(determined_keys({"A": 2, "B": 3}, [{"A", "B"}, {"A"}]), {"A", "B"})
        self.assertEqual(determined_keys({"A": 2, "B": 3, "C": 1}, [{"A", "B", "C"}, {"A", "B"}]), {"C"})
        self.assertEqual(determined_keys({"A": 2, "B": 3, "C": 1, "D": 1}, [{"A", "B", "C", "D"}, {"A", "B"}]), set())

    def test_the_zero_lower_bound_is_applied(self):
        self.assertEqual(determined_keys({"A": 0}, [{"A"}]), {"A"})
        self.assertEqual(determined_keys({"A": 0, "B": 0, "C": 0}, [{"A", "B", "C"}]), {"A", "B", "C"})
        self.assertEqual(determined_keys({"A": 1, "B": 0}, [{"A", "B"}]), set())

    def test_a_too_large_overlapping_system_is_treated_as_unsafe(self):
        counts = {k: 60 for k in "ABCD"}
        with mock.patch.object(analytics, "ENUMERATION_LIMIT", 1000):
            self.assertEqual(determined_keys(counts, [set("ABCD"), set("AB")]), set("ABCD"))

    def test_no_safe_arrangement_withholds(self):
        self.assertIsNone(self.plan({"A": (3, 2)}))  # the only real cohort is small

    def test_zero_total_with_a_small_cohort_withholds(self):
        self.assertIsNone(self.plan({"A": (0, 2), "B": (0, 30)}))

    def test_zero_total_without_small_cohorts_hides_nothing(self):
        self.assertEqual(self.plan({"A": (0, 7), "B": (0, 30)}), frozenset())

    def test_complement_choice_is_stable_when_counts_change(self):
        base = {"A": (2, 3), "B": (5, 40), "C": (4, 30)}
        first = self.plan(base)
        for b_count, c_count in ((9, 1), (1, 9), (7, 7)):
            cells = {**base, "B": (b_count, 40), "C": (c_count, 30)}
            self.assertEqual(self.plan(cells), first)

    def test_exhaustive_small_grids(self):
        # Every arrangement shown is safe by the independent check; the analytics are withheld
        # only when the total is zero with a small cohort, or no safe arrangement exists.
        rng = random.Random(4)
        for case in range(3000):
            size = rng.randint(1, 5)
            cells = {f"K{i}": (rng.randint(0, 4), rng.choice((0, 2, 4, 5, 6, 9))) for i in range(size)}
            # Some cohorts with complaints are real only through them: a known lower bound of 1.
            lower = {k: 1 for k, (n, s) in cells.items() if n and s == 0 and rng.random() < 0.6}
            with self.subTest(case=case, cells=cells, lower=lower):
                hidden = self.plan(cells, lower)
                primary = {k for k, (_, s) in cells.items() if s < MIN_ACTIVE_STUDENTS}
                total = sum(n for n, _ in cells.values())
                if hidden is None:
                    self.assertTrue(primary)
                    self.assertTrue(total == 0 or not safe_arrangement_exists(cells, lower))
                else:
                    self.assertTrue(primary <= hidden)
                    self.assert_safe(cells, hidden, lower)
                    if not primary:
                        self.assertEqual(hidden, frozenset())


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


def flatten(value, found):
    """Every int and str reachable from the analytics object, as the template could see them."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            flatten(getattr(value, field.name), found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            flatten(item, found)
    elif isinstance(value, (int, str)) and not isinstance(value, bool):
        found.add(value)
    return found


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
        region = html[html.index('<header class="sa-masthead"'):html.index('<nav class="sa-goto"')]
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
        self.assertIn(reverse("admin:academics_academicterm_changelist"), region)
        self.assertNotIn(LIST, region)
        self.assertNotIn("sa-analytics", region)
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
        self.assertIn("6 complaints were submitted in Fall 2026.", region)
        self.assertIn("1 Sep 2026 – 15 Jan 2027", region)
        cells = {cell.label: cell.count for row in overview.rows for cell in row.cells if cell.state in ("count", "zero")}
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
        self.assertEqual(overview.status_takeaway,
                         "2 of 6 are resolved (33%). 4 are not resolved: 3 are still being handled and 1 was rejected.")
        # Rejected complaints are never described as awaiting action (DEC-313).
        self.assertNotIn("awaiting", overview.status_takeaway.lower())
        self.assertIn("they are not awaiting action", region)

    def test_another_term_is_not_counted(self):
        make_term("Spring 2027", date(2027, 2, 1), date(2027, 6, 30))
        overview, _ = self.overview()
        self.assertEqual(overview.total, 0)

    def test_visible_links_drill_down_with_the_term(self):
        overview, region = self.overview()
        cohort_b = (self.a["other_batch"].pk, self.a["semester"].pk, self.a["section"].pk)
        cell = next(c for row in overview.rows for c in row.cells if c.label.startswith("Spring 2025"))
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
    def test_universe_order_and_nonexistent_cells(self):
        make_term()
        big = make_students(self.cohort(), 6)
        make_students(self.cohort(semester="other_semester", section="other_section"), 7)
        add_complaints(big[0], self.cohort(), self.cat_main, 3)
        overview, region = self.overview()
        self.assertEqual([(r.semester, r.batch) for r in overview.rows],
                         [("Semester 4", "Fall 2024"), ("Semester 5", "Fall 2024")])
        self.assertEqual(overview.sections, ("Section A", "Section B"))
        states = [[c.state for c in r.cells] for r in overview.rows]
        self.assertEqual(states, [["count", "none"], ["none", "zero"]])
        self.assertIn("No complaints", region)
        self.assertIn("no such cohort", region)

    def test_assignment_and_complaint_cohorts_are_real_and_inactive_entries_are_kept(self):
        make_term()
        inactive_batch = Batch.objects.create(name="Fall 2019", is_active=False)
        students = make_students(self.cohort(), 8)
        make_advisor(cohorts=[self.cohort(batch="other_batch")])  # no students: a real, small cohort
        add_complaints(students[0], (inactive_batch, self.a["semester"], self.a["section"]), self.cat_main, 2)
        add_complaints(students[0], self.cohort(), self.cat_main, 4)
        overview, _ = self.overview()
        labels = {c.label: c.state for r in overview.rows for c in r.cells}
        self.assertIn("Fall 2019 · Semester 4 · Section A", labels)
        self.assertEqual(labels["Spring 2025 · Semester 4 · Section A"], "hidden")
        self.assertEqual(labels["Fall 2019 · Semester 4 · Section A"], "hidden")  # no registered students

    def test_only_active_students_with_profiles_count(self):
        make_term()
        # Five profiles, one deactivated: four active students, so the cohort is suppressed.
        students = make_students(self.cohort(), 5, inactive=1)
        big = make_students(self.cohort(batch="other_batch"), 9)
        make_advisor(cohorts=[self.cohort()])  # staff are not counted
        add_complaints(students[1], self.cohort(), self.cat_main, 2)
        add_complaints(big[0], self.cohort(batch="other_batch"), self.cat_main, 3)
        overview, _ = self.overview()
        states = {c.label: c.state for r in overview.rows for c in r.cells}
        self.assertEqual(states["Fall 2024 · Semester 4 · Section A"], "hidden")
        students[0].is_active = True
        students[0].save()
        overview, _ = self.overview()
        states = {c.label: c.state for r in overview.rows for c in r.cells}
        self.assertEqual(states["Fall 2024 · Semester 4 · Section A"], "count")


class PrivacyLeakTests(OverviewTestCase):
    """A small cohort (37 complaints) and its complement (41) are hidden; nothing reveals either."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.term = make_term()
        cls.small = (cls.a["batch"], cls.a["semester"], cls.a["section"])
        cls.complement = (cls.a["other_batch"], cls.a["semester"], cls.a["section"])
        cls.visible = (cls.a["batch"], cls.a["other_semester"], cls.a["other_section"])
        small_students = make_students(cls.small, 3)
        complement_students = make_students(cls.complement, 9)  # most students: the preferred complement
        visible_students = make_students(cls.visible, 6)
        add_complaints(small_students[0], cls.small, cls.cat_main, 20, status=Status.RESOLVED)
        add_complaints(small_students[0], cls.small, cls.cat_other, 17, status=Status.RECEIVED)
        add_complaints(complement_students[0], cls.complement, cls.cat_main, 30, status=Status.UNDER_REVIEW)
        add_complaints(complement_students[0], cls.complement, cls.cat_other, 1, status=Status.RESOLVED)
        add_complaints(complement_students[0], cls.complement, cls.cat_other, 10, status=Status.REJECTED)
        add_complaints(visible_students[0], cls.visible, cls.cat_main, 12, status=Status.RECEIVED)
        # T = 90. Categories 62 / 28; statuses 21 resolved, 29 received, 30 under review, 10 rejected.
        cls.hidden_values = {37, 41}

    def test_hidden_cells_carry_no_value_or_url(self):
        overview, _ = self.overview()
        cells = {c.label: c for r in overview.rows for c in r.cells}
        for label in ("Fall 2024 · Semester 4 · Section A", "Spring 2025 · Semester 4 · Section A"):
            cell = cells[label]
            self.assertEqual((cell.state, cell.count, cell.url), ("hidden", None, None))
        self.assertEqual(cells["Fall 2024 · Semester 5 · Section B"].count, 12)
        self.assertEqual(overview.hidden_cells, 2)

    def test_no_hidden_value_in_the_context(self):
        overview, _ = self.overview()
        found = flatten(overview, set())
        self.assertFalse(self.hidden_values & found)
        for cohort in (self.small, self.complement):
            value = cohort_value(*(part.pk for part in cohort))
            self.assertFalse(any(isinstance(item, str) and value in item for item in found))

    def test_no_hidden_value_in_the_html(self):
        overview, region = self.overview()
        # Every link is one of the expected figure links: visible cells, categories and statuses.
        # (Links carry database ids, which on a kept MySQL test database can equal any number.)
        expected_links = {c.url for r in overview.rows for c in r.cells if c.url}
        expected_links |= {c.url for c in overview.categories}
        expected_links |= {overview.resolved.url} | {p.url for p in overview.not_resolved_parts}
        links = {href.replace("&amp;", "&") for href in re.findall(r'href="([^"]*)"', region)}
        self.assertEqual(links, expected_links)
        self.assertEqual(len([c for r in overview.rows for c in r.cells if c.url]), 1)  # only the visible cohort
        # Everything else on the page (text and every other attribute) never shows a hidden value.
        without_links = re.sub(r'href="[^"]*"', "", region)
        for number in self.hidden_values:
            self.assertIsNone(re.search(rf"\b{number}\b", without_links), number)
        for cohort in (self.small, self.complement):
            self.assertNotIn(f"cohort={cohort_value(*(part.pk for part in cohort))}", region)
        self.assertIn(f"cohort={cohort_value(*(part.pk for part in self.visible))}", region)
        self.assertEqual(set(re.findall(r"data-([a-z-]+)=", region)), {"section"})
        self.assertNotIn("<script", region)
        self.assertNotIn('type="hidden"', region)
        self.assertEqual(region.count("sa-cell--hidden\""), 2)  # plus the key swatch
        self.assertNotIn("title=", region)

    def test_hidden_values_cannot_be_reconstructed_from_everything_displayed(self):
        overview, _ = self.overview()
        total_from_categories = sum(c.count for c in overview.categories)
        total_from_statuses = overview.resolved.count + sum(p.count for p in overview.not_resolved_parts)
        self.assertEqual(total_from_categories, total_from_statuses)
        self.assertEqual(total_from_categories, overview.total)  # T is known (spec 6.4)
        visible = {c.label: c.count for r in overview.rows for c in r.cells if c.count is not None}
        hidden = {c.label: None for r in overview.rows for c in r.cells if c.state == "hidden"}
        # The observer knows only that the hidden cells add up to T minus the visible cells.
        remainder = overview.total - sum(visible.values())
        self.assertEqual(remainder, 78)
        self.assertEqual(len(hidden), 2)
        true_counts = dict(zip(sorted(hidden), (37, 41)))
        self.assertEqual(brute_force_determined(true_counts, overview.total, visible), set())

    def test_takeaways_describe_only_cohorts_shown(self):
        overview, region = self.overview()
        self.assertEqual(overview.cohort_takeaway,
                         "Fall 2024 · Semester 5 · Section B has the most complaints among the cohorts shown: 12 complaints.")
        self.assertIn("Hidden for privacy", region)
        self.assertNotIn("anonym", region.lower())


class ComplaintOnlyCohortTests(OverviewTestCase):
    """Review regression: a cohort with no students or advisor, real only through this term's
    complaints, shows on the map that it has at least one complaint."""

    def test_its_lower_bound_cannot_pin_the_hidden_values(self):
        make_term()
        old = Batch.objects.create(name="Fall 2019", is_active=False)
        complement = make_students(self.cohort(), 9)  # most students: the usual complement, 0 complaints
        other = make_students(self.cohort(batch="other_batch", section="other_section"), 6)
        add_complaints(other[0], (old, self.a["semester"], self.a["section"]), self.cat_main, 1)
        add_complaints(other[0], self.cohort(batch="other_batch", section="other_section"), self.cat_main, 5)
        overview, region = self.overview()
        self.assertEqual(overview.state, "ready")
        cells = {c.label: c for r in overview.rows for c in r.cells}
        hidden = {label for label, c in cells.items() if c.state == "hidden"}
        visible = {label: c.count for label, c in cells.items() if c.count is not None}
        true_counts = {"Fall 2019 · Semester 4 · Section A": 1, "Spring 2025 · Semester 4 · Section B": 5}
        self.assertEqual(hidden, set(true_counts))
        lower = {"Fall 2019 · Semester 4 · Section A": 1}
        self.assertEqual(brute_force_determined(true_counts, overview.total, visible, lower), set())
        self.assertEqual(cells["Fall 2024 · Semester 4 · Section A"].state, "zero")
        self.assertNotIn("cohort=" + cohort_value(old.pk, self.a["semester"].pk, self.a["section"].pk), region)


class WithheldStateTests(OverviewTestCase):
    def withheld_region(self):
        overview, region = self.overview()
        self.assertEqual(overview.state, "withheld")
        self.assertIn("Figures for Fall 2026 are withheld.", region)
        self.assertNotIn(LIST, region)
        self.assertNotIn("sa-analytics", region)
        text = re.sub(r"<[^>]+>", " ", region)  # visible text only (tag names such as h1 carry digits)
        digits = re.findall(r"\d+", text.replace("1 Sep 2026 – 15 Jan 2027", "").replace("1 Jan 2025 – 30 Jun 2025", "").replace("Fall 2026", ""))
        self.assertEqual(digits, [])
        return region

    def test_zero_total_with_a_small_cohort(self):
        # DEC-319 (a): T = 0 would show that the small cohort has no complaints.
        make_term()
        make_students(self.cohort(), 3)
        make_students(self.cohort(batch="other_batch"), 9)
        self.withheld_region()

    def test_only_real_cohort_is_small(self):
        # DEC-319 (b): with one real cohort, T itself is that cohort's count.
        make_term()
        small = make_students(self.cohort(), 3)
        add_complaints(small[0], self.cohort(), self.cat_main, 3)
        self.withheld_region()

    def test_both_withheld_cases_render_identically(self):
        term = make_term()
        small = make_students(self.cohort(), 3)
        add_complaints(small[0], self.cohort(), self.cat_main, 3)
        only_small_cohort = self.withheld_region()  # case (b)
        # Move the window away from the complaints: T = 0 with a small cohort, case (a).
        AcademicTerm.objects.filter(pk=term.pk).update(start_date=date(2025, 1, 1), end_date=date(2025, 6, 30))
        make_students(self.cohort(batch="other_batch"), 9)
        overview, zero_total = self.overview()
        self.assertEqual(overview.state, "withheld")

        def normalise(html):
            return html.replace("1 Jan 2025 – 30 Jun 2025", "DATES").replace("1 Sep 2026 – 15 Jan 2027", "DATES")

        self.assertEqual(normalise(zero_total), normalise(only_small_cohort))


class EmptyTermTests(OverviewTestCase):
    def test_no_complaints_and_no_small_cohorts(self):
        make_term()
        make_students(self.cohort(), 5)
        overview, region = self.overview()
        self.assertEqual((overview.state, overview.total), ("ready", 0))
        self.assertIn("No complaints have been submitted in Fall 2026.", region)
        self.assertEqual(overview.resolved.percent_label, "")
        self.assertIn("No complaints this term", region)
        self.assertNotIn("sa-stack", region)


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

    def test_complaint_list_access_is_unchanged_for_hidden_cohorts(self):
        # DEC-320: suppression limits the analytics output, not operational record access.
        make_term()
        small = make_students(self.cohort(), 3)
        make_students(self.cohort(batch="other_batch"), 9)
        add_complaints(small[0], self.cohort(), self.cat_main, 2)
        term = AcademicTerm.objects.get()
        url = f"{LIST}?cohort={cohort_value(*(p.pk for p in self.cohort()))}&term={term.pk}"
        self.assertEqual(self.client.get(url).context["page"].paginator.count, 2)
