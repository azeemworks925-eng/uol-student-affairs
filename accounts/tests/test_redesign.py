"""The redesigned shell, dashboards, list and detail pages, and the meetings week view (DEC-329)."""

import re
from datetime import time, timedelta
from unittest import mock

from django.contrib.staticfiles import finders
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.dashboards import bar_rows, line_chart, shade, stacked
from accounts.representation import Cohort, appoint_representatives
from accounts.templatetags.ui import ago, initials
from complaints import services as complaint_services
from complaints.analytics import Overview
from complaints.models import Complaint, ComplaintCategory
from complaints.tests.test_analytics import add_complaints, make_students, make_term
from meetings import services as meeting_services
from meetings.models import Meeting
from meetings.presentation import iso_week, local_datetime, parse_week
from notifications.models import Notification
from voice import services as voice_services

from .helpers import cohort, make_academics, make_advisor, make_student, make_super_admin

Status = Complaint.Status
DESCRIPTION = "A description that is long enough to be accepted by the complaint form."


def between(html, start, end):
    first = html.index(start)
    return html[first:html.index(end, first)]


def main(response):
    html = response.content.decode()
    return html[html.index("<main"):html.index("</main>")]


class RedesignTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_academics()
        cls.home = cohort(cls.a)
        cls.other = cohort(cls.a, section="other_section")
        cls.student = make_student(academics=cls.a, full_name="Ali Khan")
        cls.classmate = make_student("70000001@student.uol.edu.pk", academics=cls.a, cohort=cls.home, full_name="Sara Malik")
        cls.outsider = make_student("70000002@student.uol.edu.pk", academics=cls.a, cohort=cls.other, full_name="Omar Farooq")
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.other_advisor = make_advisor("advisor2@uol.edu.pk", cohorts=[cls.other], full_name="Mr. Bilal Shah")
        cls.admin = make_super_admin()
        cls.category = ComplaintCategory.objects.create(name="Redesign Category", position=90)
        cls.mine = complaint_services.submit_complaint(cls.student, category=cls.category, title="My own lab problem", description=DESCRIPTION)
        cls.classmates = complaint_services.submit_complaint(cls.classmate, category=cls.category, title="A classmate's problem", description=DESCRIPTION)
        cls.theirs = complaint_services.submit_complaint(cls.outsider, category=cls.category, title="Another section's problem", description=DESCRIPTION)

    def get(self, user, name, *args, **params):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args), params)


class ShellTests(RedesignTestCase):
    def users(self):
        return ((self.student, "student_home"), (self.advisor, "advisor_home"), (self.admin, "super_admin_home"))

    def test_every_role_gets_the_same_shell(self):
        for user, home in self.users():
            with self.subTest(role=user.role):
                html = self.get(user, home).content.decode()
                for piece in ('<header class="sa-topbar">', '<aside class="sa-sidebar"', "data-sidebar-toggle", 'id="sa-drawer"',
                              "data-quick-search", 'class="dropdown sa-new"', 'class="dropdown sa-bell"', 'class="dropdown sa-account"',
                              "js/app.js"):
                    self.assertIn(piece, html)

    def test_sidebar_items_per_role(self):
        expected = {
            self.student: ["Home", "Complaints", "Student Voice", "Meetings"],
            self.advisor: ["Overview", "Complaints", "Collective Issues", "Student Voice", "Meetings", "Representatives"],
            self.admin: ["Overview", "Complaints", "Collective Issues", "Student Voice", "Meetings", "Students", "Staff",
                         "CR/GR Management", "Academic Structure", "Academic Terms", "Complaint Categories"],
        }
        for user, home in self.users():
            with self.subTest(role=user.role):
                sidebar = between(self.get(user, home).content.decode(), '<aside class="sa-sidebar"', "</aside>")
                self.assertEqual(re.findall(r'data-tip="([^"]+)"', sidebar), expected[user])
                self.assertNotIn("/notifications/", sidebar)
                self.assertNotIn("Sign out", sidebar)

    def test_new_menu_per_role(self):
        expected = {
            self.student: ["New complaint", "Student Voice", "Request meeting"],
            self.advisor: ["Schedule meeting"],
            self.admin: ["Add Batch Advisor"],
        }
        for user, home in self.users():
            with self.subTest(role=user.role):
                menu = between(self.get(user, home).content.decode(), 'class="dropdown sa-new"', "</ul>")
                labels = re.findall(r"</svg>([^<]+)</a>", menu)
                self.assertEqual(labels, expected[user])
                for url in re.findall(r'<a [^>]*href="([^"]+)"', menu):
                    self.assertEqual(self.client.get(url.replace("&amp;", "&")).status_code, 200)

    def test_bell_shows_the_count_and_latest_five(self):
        for number in range(7):
            complaint_services.respond(self.advisor, self.mine, f"Response number {number}")
        html = self.get(self.student, "student_home").content.decode()
        bell = between(html, 'class="dropdown sa-bell"', '<a class="sa-bell-all"')
        self.assertIn('<span class="sa-badge sa-badge--dot" aria-hidden="true">7</span>', bell)
        self.assertEqual(bell.count('class="sa-bell-item'), 5)
        self.assertEqual(bell.count("is-unread"), 5)
        newest = Notification.objects.filter(recipient=self.student).order_by("-created_at", "-id").first()
        self.assertIn(f'action="{reverse("notification_open", args=[newest.pk])}"', bell)
        self.assertIn('<a class="sa-bell-all" href="/notifications/">See all</a>', html)

    def test_bell_never_lists_someone_elses_notifications(self):
        complaint_services.respond(self.advisor, self.classmates, "Only for the classmate")
        bell = between(self.get(self.student, "student_home").content.decode(), 'class="dropdown sa-bell"', '<a class="sa-bell-all"')
        self.assertNotIn("sa-bell-item", bell)

    def test_avatar_menu(self):
        menu = between(self.get(self.student, "student_home").content.decode(), 'class="dropdown sa-account"', "</form>")
        for text in ("Ali Khan", self.student.email, "Student", "A · S4", "Sign out", f'action="{reverse("account_logout")}"'):
            self.assertIn(text, menu)
        staff_menu = between(self.get(self.advisor, "advisor_home").content.decode(), 'class="dropdown sa-account"', "</form>")
        self.assertIn("Batch Advisor", staff_menu)
        self.assertNotIn("sa-cohort", staff_menu)

    def test_cohort_chip_is_short_with_the_full_name_in_its_tooltip(self):
        html = self.get(self.student, "student_home").content.decode()
        self.assertIn('<span class="sa-cohort" title="Fall 2024 · Semester 4 · Section A">A · S4', html)

    def test_breadcrumb_names_the_record(self):
        response = self.get(self.advisor, "advisor_complaint_detail", self.mine.reference)
        crumbs = between(response.content.decode(), '<nav class="sa-crumbs"', "</nav>")
        self.assertIn("Complaints", crumbs)
        self.assertIn(self.mine.reference, crumbs)


class QuickSearchTests(RedesignTestCase):
    def search(self, user, text):
        self.client.force_login(user)
        return self.client.get(reverse("quick_search"), {"q": text})

    def test_signed_out_visitors_are_sent_to_sign_in(self):
        response = self.client.get(reverse("quick_search"), {"q": "ali"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_a_reference_jumps_to_the_complaint_for_each_role(self):
        for user, name in ((self.student, "student_complaint_detail"), (self.advisor, "advisor_complaint_detail"),
                           (self.admin, "super_admin_complaint_detail")):
            with self.subTest(role=user.role):
                response = self.search(user, f"  {self.mine.reference.lower()} ")
                self.assertRedirects(response, reverse(name, args=[self.mine.reference]))

    def test_student_cannot_find_other_peoples_complaints(self):
        for text in (self.classmates.reference, self.theirs.reference, "classmate", "Sara", "Omar", "70000001"):
            with self.subTest(text=text):
                response = self.search(self.student, text)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["results"].total, 0)
                body = main(response)
                self.assertNotIn(self.classmates.title, body)
                self.assertNotIn("Sara Malik", body)

    def test_student_finds_their_own(self):
        results = self.search(self.student, "lab problem").context["results"]
        self.assertEqual([c.reference for c in results.complaints], [self.mine.reference])
        self.assertEqual(results.students, [])

    def test_advisor_sees_only_assigned_cohorts(self):
        response = self.search(self.advisor, self.theirs.reference)
        self.assertEqual(response.status_code, 200)  # the same "no results" as a reference that does not exist
        self.assertEqual(response.context["results"].total, 0)
        self.assertEqual(self.search(self.advisor, "Omar").context["results"].total, 0)
        self.assertEqual(self.search(self.advisor, "70000002").context["results"].total, 0)

    def test_advisor_finds_students_by_name_and_sap_id(self):
        for text in ("Sara", "malik", "70000001"):
            with self.subTest(text=text):
                results = self.search(self.advisor, text).context["results"]
                self.assertEqual([s["name"] for s in results.students], ["Sara Malik"])
                self.assertEqual([c.reference for c in results.complaints], [self.classmates.reference])

    def test_a_missing_reference_looks_the_same_as_a_hidden_one(self):
        hidden = main(self.search(self.advisor, self.theirs.reference)).replace(self.theirs.reference, "REF")
        missing = main(self.search(self.advisor, "CMP-2099-99999")).replace("CMP-2099-99999", "REF")
        self.assertEqual(hidden, missing)

    def test_super_admin_finds_across_the_department(self):
        results = self.search(self.admin, "Omar").context["results"]
        self.assertEqual([c.reference for c in results.complaints], [self.theirs.reference])


class DashboardNumberTests(RedesignTestCase):
    def values(self, response):
        return {stat["label"]: stat["value"] for stat in response.context["dashboard"]["stats"]}

    def test_student_sees_only_their_own_numbers(self):
        complaint_services.change_status(self.advisor, self.classmates, Status.RESOLVED, "Done for the classmate.")
        submission = voice_services.submit(self.student, type="question", text="When is the final exam timetable due?")
        voice_services.answer(self.advisor, submission, "On Friday.")
        voice_services.submit(self.classmate, type="question", text="A question from somebody else entirely.")
        response = self.get(self.student, "student_home")
        self.assertEqual(self.values(response), {"Open complaints": 1, "Resolved complaints": 0, "Student Voice answers": 1, "Upcoming meetings": 0})
        body = main(response)
        self.assertNotIn(self.classmates.title, body)
        self.assertNotIn("<svg viewBox", body)  # no charts for students
        self.assertIn("sa-journey", body)

    def test_advisor_numbers_cover_assigned_cohorts_only(self):
        complaint_services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW)
        complaint_services.change_status(self.advisor, self.classmates, Status.RESOLVED, "Done.")
        voice_services.submit(self.student, type="idea", text="An idea that is waiting for a review.")
        voice_services.submit(self.outsider, type="idea", text="An idea from a cohort that is not assigned.")
        response = self.get(self.advisor, "advisor_home")
        self.assertEqual(self.values(response), {"Open": 1, "Received": 0, "Under review": 1, "Resolved (7 days)": 1})
        self.assertEqual(response.context["dashboard"]["voice_waiting"], 1)
        self.assertNotIn(self.theirs.reference, main(response))

    def test_advisor_activity_hides_owner_changes(self):
        complaint_services.assign_responsible(self.admin, self.mine, self.advisor)
        activity = self.get(self.advisor, "advisor_home").context["dashboard"]["activity"]
        self.assertTrue(activity)
        self.assertFalse([item for item in activity if "owner" in item["what"]])

    def test_advisor_upcoming_meetings(self):
        start = local_datetime(timezone.localdate() + timedelta(days=3), time(10, 0))
        meeting_services.schedule(self.advisor, self.student, reason="Talk about the elective choice.", starts_at=start, duration=30, location="Room 1")
        response = self.get(self.advisor, "advisor_home")
        self.assertEqual([m.student for m in response.context["dashboard"]["meetings"]], [self.student])

    def test_greeting_skips_a_title(self):
        self.assertContains(self.get(self.advisor, "advisor_home"), ", Ayesha.")


class OverviewSuppressionTests(TestCase):
    """Hidden cohort values never reach the HTML, attributes or chart data of the new cards."""

    @classmethod
    def setUpTestData(cls):
        cls.a = make_academics()
        cls.admin = make_super_admin()
        cls.category = ComplaintCategory.objects.create(name="Redesign Category", position=90)
        cls.term = make_term()
        cls.small = (cls.a["batch"], cls.a["semester"], cls.a["section"])
        cls.complement = (cls.a["other_batch"], cls.a["semester"], cls.a["section"])
        cls.visible = (cls.a["batch"], cls.a["other_semester"], cls.a["other_section"])
        cls.small_students = make_students(cls.small, 3)
        cls.complement_students = make_students(cls.complement, 9)
        cls.visible_students = make_students(cls.visible, 6)
        add_complaints(cls.small_students[0], cls.small, cls.category, 37, status=Status.RECEIVED)
        add_complaints(cls.complement_students[0], cls.complement, cls.category, 20, status=Status.UNDER_REVIEW)
        add_complaints(cls.complement_students[0], cls.complement, cls.category, 21, status=Status.RESOLVED)
        add_complaints(cls.visible_students[0], cls.visible, cls.category, 12, status=Status.RECEIVED)
        for student in (cls.small_students[0], cls.complement_students[0], cls.visible_students[0]):
            complaint = Complaint.objects.filter(student=student).first()
            complaint.reference = f"CMP-2026-{complaint.pk:05d}"  # bulk_create assigns no reference
            QuerySet(Complaint).filter(pk=complaint.pk).update(reference=complaint.reference)
            complaint_services.respond(cls.admin, complaint, "A response that creates an event.")
            complaint_services.add_further_information(student, complaint, "More detail from the student.")

    def overview(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("super_admin_home"))
        region = re.sub(r'<p class="sa-greeting-date">.*?</p>', "", main(response))
        return response, region

    def test_activity_covers_only_visible_cohorts_and_names_no_student(self):
        response, region = self.overview()
        activity = response.context["dashboard"]["activity"]
        self.assertTrue(activity)
        with_reference = Complaint.objects.exclude(reference=None)
        visible_refs = set(with_reference.filter(student=self.visible_students[0]).values_list("reference", flat=True))
        hidden_refs = with_reference.exclude(student=self.visible_students[0]).values_list("reference", flat=True)
        self.assertEqual(len(hidden_refs), 2)
        for item in activity:
            self.assertTrue(any(ref in item["what"] for ref in visible_refs), item)
            self.assertEqual(item["url"], "")
        for reference in hidden_refs:
            self.assertNotIn(reference, region)
        for student in (*self.small_students, *self.complement_students, *self.visible_students):
            self.assertNotIn(student.full_name, region)
        self.assertIn("A student", region)

    def test_no_hidden_value_in_any_new_card(self):
        response, region = self.overview()
        without_links = re.sub(r'href="[^"]*"', "", region)
        without_links = re.sub(r"CMP-\d{4}-\d+", "", without_links)
        without_links = re.sub(r'datetime="[^"]*"', "", without_links)  # a clock time can contain 37 or 41
        for number in (37, 41):
            self.assertIsNone(re.search(rf"(?<![\d.]){number}(?![\d.])", without_links), number)
        data = response.context["dashboard"]
        self.assertEqual([row["value"] for row in data["section_bars"]], [12])  # only the visible cohort is charted
        self.assertEqual(sum(1 for row in data["grid_rows"] for item in row["cells"] if item["cell"].state == "hidden"), 2)
        self.assertFalse([item for row in data["grid_rows"] for item in row["cells"] if item["cell"].state == "hidden" and item["shade"]])

    def test_shading_is_scaled_to_visible_cells(self):
        _, region = self.overview()
        self.assertIn("sa-cell sa-cell--count sa-shade-4", region)  # the largest visible cell, however large the hidden ones are
        self.assertEqual(region.count("sa-shade-"), 1)

    def test_withheld_state_has_no_cards(self):
        self.client.force_login(self.admin)
        with mock.patch("accounts.views.build_overview", return_value=Overview(state="withheld", term=self.term)):
            response = self.client.get(reverse("super_admin_home"))
        region = main(response)
        self.assertEqual(response.context["dashboard"], {})
        for piece in ("sa-stats", "sa-analytics", "sa-activity", "<svg viewBox"):
            self.assertNotIn(piece, region)


class ChartGeometryTests(SimpleTestCase):
    def test_line_chart(self):
        self.assertIsNone(line_chart(["a", "b"], [0, 0]))
        chart = line_chart(["a", "b", "c"], [0, 2, 4])
        self.assertEqual(chart["y_ticks"], [4, 2, 0])
        self.assertEqual(chart["path"], "M0 100 L50 50 L100 0")
        self.assertEqual(chart["desc"], "a: 0; b: 2; c: 4")

    def test_bars_scale_to_the_largest_value(self):
        self.assertEqual([r["width"] for r in bar_rows([{"value": 2}, {"value": 4}, {"value": 0}])], ["50", "100", "0"])
        self.assertEqual(bar_rows([{"value": 0}])[0]["width"], "0")

    def test_stacked_skips_empty_segments(self):
        drawn = stacked([{"key": "a", "value": 1}, {"key": "b", "value": 0}, {"key": "c", "value": 3}])
        self.assertEqual([(s["key"], s["x"], s["width"]) for s in drawn], [("a", "0", "25"), ("c", "25", "75")])
        self.assertEqual(stacked([{"key": "a", "value": 0}]), [])

    def test_shade_levels(self):
        self.assertEqual([shade(n, 8) for n in (0, 1, 2, 3, 4, 8)], [0, 1, 1, 2, 2, 4])

    def test_initials_and_relative_time(self):
        self.assertEqual(initials("Dr. Ayesha Rahman"), "AR")
        self.assertEqual(initials("Ali"), "A")
        self.assertEqual(initials(""), "?")
        self.assertEqual(ago(timezone.now()), "just now")
        self.assertEqual(ago(timezone.now() - timedelta(hours=3)), "3h ago")


class ListAndDetailTests(RedesignTestCase):
    def test_list_cards_toggle_on_every_list(self):
        pages = ((self.student, "student_complaints", "student-complaints"), (self.advisor, "advisor_complaints", "staff-complaints"),
                 (self.admin, "super_admin_complaints", "staff-complaints"))
        for user, name, key in pages:
            with self.subTest(page=name):
                html = self.get(user, name).content.decode()
                self.assertIn(f'data-view-toggle="{key}"', html)
                self.assertIn(f'data-view="list" data-view-key="{key}"', html)
                self.assertIn('data-view-choice="cards"', html)
                self.assertIn("sa-item--received", html)
                self.assertEqual(html.count('class="sa-stat '), 4)

    def test_student_list_has_no_student_column(self):
        collection = between(self.get(self.student, "student_complaints").content.decode(), '<ul class="sa-collection', "</ul>")
        self.assertIn("sa-collection--no-who", collection)
        self.assertNotIn("sa-item-who", collection)

    def test_filter_links_keep_the_other_filters_and_reset_the_page(self):
        html = self.get(self.advisor, "advisor_complaints", status="received", sort="oldest", page="1").content.decode()
        self.assertIn(f'href="{reverse("advisor_complaints")}?status=open&amp;sort=oldest"', html)

    def test_back_link_keeps_the_list_state(self):
        html = self.get(self.student, "student_complaint_detail", self.mine.reference, status="received", sort="oldest").content.decode()
        self.assertIn(f'class="sa-back" href="{reverse("student_complaints")}?status=received&amp;sort=oldest"', html)

    def test_advisor_panel(self):
        html = self.get(self.advisor, "advisor_complaint_detail", self.mine.reference).content.decode()
        panel = between(html, '<aside class="sa-detail-side"', "</aside>")
        for text in ("Ali Khan", "12345678", "Case details", "Last activity", "Dr. Ayesha Rahman", 'data-dialog-open="dialog-respond"', 'data-dialog-open="dialog-status"'):
            self.assertIn(text, panel)
        self.assertNotIn("sa-post-badge", panel)
        self.assertNotIn("owner", panel.lower())  # the owner stays Super Admin only (DEC-310)
        self.assertNotIn(self.student.email, html)  # P3-1

    def test_super_admin_panel_has_the_owner_control(self):
        html = self.get(self.admin, "super_admin_complaint_detail", self.mine.reference).content.decode()
        panel = between(html, '<aside class="sa-detail-side"', "</aside>")
        self.assertIn("Responsible owner", panel)
        self.assertIn('data-dialog-open="dialog-owner"', panel)
        self.assertIn(f'action="{reverse("super_admin_complaint_owner", args=[self.mine.reference])}"', html)

    def test_cr_and_gr_badges(self):
        appoint_representatives(self.advisor, Cohort(*(part.pk for part in self.home)), cr=self.student, gr=self.classmate)
        for complaint, post in ((self.mine, "CR"), (self.classmates, "GR")):
            with self.subTest(post=post):
                panel = between(self.get(self.advisor, "advisor_complaint_detail", complaint.reference).content.decode(), '<aside class="sa-detail-side"', "</aside>")
                self.assertIn(f'<span class="sa-post-badge">{post}</span>', panel)

    def test_student_view_has_no_student_card_and_their_own_actions(self):
        html = self.get(self.student, "student_complaint_detail", self.mine.reference).content.decode()
        panel = between(html, '<aside class="sa-detail-side"', "</aside>")
        self.assertNotIn("sa-person", panel)
        self.assertIn('data-dialog-open="dialog-information"', panel)
        self.assertIn('data-dialog-open="dialog-cancel"', panel)
        self.assertNotIn('data-dialog-open="dialog-still"', panel)
        complaint_services.change_status(self.advisor, self.mine, Status.RESOLVED, "Fixed.")
        panel = between(self.get(self.student, "student_complaint_detail", self.mine.reference).content.decode(), '<aside class="sa-detail-side"', "</aside>")
        self.assertIn('data-dialog-open="dialog-still"', panel)

    def test_voice_detail_panel(self):
        submission = voice_services.submit(self.student, type="question", text="When will the timetable be published?")
        advisor = self.get(self.advisor, "advisor_voice_detail", submission.pk).content.decode()
        self.assertIn('data-dialog-open="dialog-answer"', advisor)
        admin = self.get(self.admin, "super_admin_voice_detail", submission.pk).content.decode()
        self.assertNotIn("dialog-answer", admin)
        self.assertIn("Read-only oversight", admin)


class WeekViewTests(RedesignTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.monday = self.today - timedelta(days=self.today.weekday()) + timedelta(days=7)
        self.week = iso_week(self.monday)

    def book(self, student, day_offset, at, duration=30):
        return meeting_services.schedule(self.advisor, student, reason="Talk about the elective choice.",
                                         starts_at=local_datetime(self.monday + timedelta(days=day_offset), at),
                                         duration=duration, location="Room 1")

    def test_parse_week(self):
        monday = self.today - timedelta(days=self.today.weekday())
        for bad in ("", None, "nonsense", "2026-W99", "2026-W00", "1999-W10", "2026-11"):
            with self.subTest(value=bad):
                self.assertEqual(parse_week(bad, self.today), monday)
        self.assertEqual(parse_week("2026-W48", self.today).isoformat(), "2026-11-23")

    def test_invalid_week_shows_the_current_week(self):
        response = self.get(self.advisor, "advisor_meetings_week", week="2026-W99")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["week"]["week"], iso_week(self.today))

    def test_navigation_links(self):
        response = self.get(self.student, "student_meetings_week", week="2026-W01")
        self.assertContains(response, 'href="?week=2025-W52"')
        self.assertContains(response, 'href="?week=2026-W02"')
        self.assertContains(response, f'href="?week={iso_week(self.today)}"')

    def test_meeting_is_placed_by_time_and_sized_by_duration(self):
        meeting = self.book(self.student, 2, time(10, 0), 45)
        response = self.get(self.advisor, "advisor_meetings_week", week=self.week)
        day = response.context["week"]["days"][2]
        self.assertEqual([item["meeting"].pk for item in day["items"]], [meeting.pk])
        self.assertContains(response, "grid-row: 25 / span 9; grid-column: 1 / span 1")  # (10:00 - 08:00) / 5 min + 1, 45 / 5
        self.assertContains(response, f'href="{reverse("advisor_meeting_detail", args=[meeting.pk])}"')

    def test_range_extends_to_fit_early_and_late_meetings(self):
        self.book(self.student, 0, time(7, 15), 30)
        self.book(self.classmate, 1, time(19, 0), 60)
        week = self.get(self.advisor, "advisor_meetings_week", week=self.week).context["week"]
        self.assertEqual(week["slots"][0]["label"], "07:00")
        self.assertEqual(week["slots"][-1]["label"], "19:30")

    def test_overlapping_meetings_sit_side_by_side(self):
        self.book(self.student, 3, time(10, 0), 30)
        self.book(self.classmate, 3, time(10, 15), 30)
        day = self.get(self.advisor, "advisor_meetings_week", week=self.week).context["week"]["days"][3]
        self.assertEqual([(item["lane"], item["lanes"]) for item in day["items"]], [(1, 2), (2, 2)])
        self.assertEqual(day["lanes"], 2)

    def test_scoping(self):
        self.book(self.student, 1, time(9, 0))
        other = self.get(self.other_advisor, "advisor_meetings_week", week=self.week)
        self.assertFalse(other.context["week"]["has_meetings"])
        classmate = self.get(self.classmate, "student_meetings_week", week=self.week)
        self.assertFalse(classmate.context["week"]["has_meetings"])
        self.assertTrue(self.get(self.student, "student_meetings_week", week=self.week).context["week"]["has_meetings"])

    def test_requests_without_an_agreed_time_are_not_placed(self):
        when = local_datetime(self.monday, time(11, 0))
        meeting_services.request_meeting(self.student, reason="I would like some advice please.", preferred_at=when)
        self.assertFalse(self.get(self.advisor, "advisor_meetings_week", week=self.week).context["week"]["has_meetings"])

    def test_phone_day_tabs(self):
        day = self.monday + timedelta(days=4)
        response = self.get(self.student, "student_meetings_week", week=self.week, day=day.isoformat())
        self.assertEqual([d["is_selected"] for d in response.context["week"]["days"]], [False] * 4 + [True] + [False] * 2)
        self.assertContains(response, "sa-week-tabs")

    def test_view_switcher_on_every_role(self):
        for user, name in ((self.student, "student_meetings"), (self.advisor, "advisor_meetings"), (self.admin, "super_admin_meetings")):
            with self.subTest(page=name):
                response = self.get(user, name)
                self.assertContains(response, 'data-meeting-views="list"')
                self.assertContains(response, f'href="{reverse(name + "_week")}"')
                self.assertContains(response, f'href="{reverse(name + "_month")}"')

    def test_super_admin_pages_are_read_only(self):
        meeting = self.book(self.student, 1, time(9, 0))
        for name, args in (("super_admin_meetings_month", ()), ("super_admin_meetings_week", ()), ("super_admin_meeting_detail", (meeting.pk,))):
            with self.subTest(page=name):
                response = self.get(self.admin, name, *args)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('method="post"', main(response))
                self.assertNotContains(response, "calendar.google.com")
        for action in ("confirm", "suggest", "decline", "cancel"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"super_admin_meeting_{action}", args=[meeting.pk])

    def test_other_roles_cannot_open_super_admin_meeting_pages(self):
        meeting = self.book(self.student, 1, time(9, 0))
        for user in (self.student, self.advisor):
            self.client.force_login(user)
            for url in (reverse("super_admin_meetings_week"), reverse("super_admin_meeting_detail", args=[meeting.pk])):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_meeting_status_filter_is_unchanged(self):
        self.book(self.student, 1, time(9, 0))
        response = self.get(self.admin, "super_admin_meetings", status=Meeting.Status.DECLINED)
        self.assertContains(response, "No meetings match these filters.")


class MotionCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(finders.find("css/app.css"), encoding="utf-8") as file:
            cls.css = file.read()

    def test_motion_tokens(self):
        for token in ("--dur-fast: 120ms", "--dur-base: 200ms", "--dur-slow: 320ms", "--ease-out: cubic-bezier(0.2, 0, 0, 1)"):
            self.assertIn(token, self.css)

    def test_reduced_motion_turns_everything_off(self):
        block = self.css[self.css.index("@media (prefers-reduced-motion: reduce)"):]
        self.assertIn("animation: none !important", block)
        self.assertIn("transition: none !important", block)

    def test_only_the_motion_tokens_set_durations(self):
        for rule in re.findall(r"(?:transition|animation):[^;}]*", self.css):
            if "none" in rule:
                continue
            self.assertIn("var(--dur-", rule, rule)
            self.assertNotRegex(rule, r"\b\d+m?s\b")
        self.assertNotIn("infinite", self.css)
