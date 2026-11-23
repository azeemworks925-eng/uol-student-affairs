"""Complaints, finished: merge-sorted lists, "Go to reference" (hash table), trie search,
"Next complaint" (min-heap), the real Student Home and the Batch Advisor Overview counts."""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.messages import get_messages
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from complaints import ordering, services
from complaints.models import Complaint
from complaints.workspace import PAGE_SIZE, cohort_value
from notifications.models import Notification
from notifications import services as notification_services

from .helpers import OTHER_STUDENT_EMAIL, cohort, make_academics, make_advisor, make_categories, make_student, make_super_admin, submit

Status = Complaint.Status
ADVISOR_LIST = reverse("advisor_complaints")
ADMIN_LIST = reverse("super_admin_complaints")
STUDENT_LIST = reverse("student_complaints")
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=dt_timezone.utc)


def at(days, minutes=0):
    """Patch the clock so a service call happens at T0 + days."""
    return mock.patch("django.utils.timezone.now", return_value=T0 + timedelta(days=days, minutes=minutes))


def refs(response):
    return [c.reference for c in response.context["page"].object_list]


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class CompleteTestCase(TestCase):
    """Five complaints with known times, categories and statuses, in two cohorts.

    home (Fall 2024 · 4 · A): a1 Ali/Academic (day 0), z1 Zara/Other (day 1), a2 Ali/Other (day 2),
    z2 Zara/Academic (day 3). away (Spring 2025 · 4 · A): o1 Omar/Academic (day 4).
    Activity: a1 gets a response on day 5, so it has the latest activity.
    Statuses: a1 Under Review, z1 Resolved, a2 Received, z2 Rejected, o1 Received.
    """

    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        cls.categories = make_categories()  # "Test Academic", "Test Other"
        cls.home, cls.away = cohort(a), cohort(a, batch="other_batch")
        cls.ali = make_student(academics=a, full_name="Ali Khan")  # 12345678
        cls.zara = make_student(OTHER_STUDENT_EMAIL, academics=a, full_name="Zara Ahmed")  # 87654321
        cls.omar = make_student("22223333@student.uol.edu.pk", academics=a, cohort=cls.away, full_name="Omar Farooq")
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.admin = make_super_admin()
        academic, other = cls.categories["academic"], cls.categories["other"]
        with at(0):
            cls.a1 = submit(cls.ali, academic, title="Lab timetable clash")
        with at(1):
            cls.z1 = submit(cls.zara, other, title="Library hours")
        with at(2):
            cls.a2 = submit(cls.ali, other, title="Water cooler empty")
        with at(3):
            cls.z2 = submit(cls.zara, academic, title="Quiz marks missing")
        with at(4):
            cls.o1 = submit(cls.omar, academic, title="Other batch complaint")
        with at(4, 10):
            services.change_status(cls.advisor, cls.a1, Status.UNDER_REVIEW)
            services.change_status(cls.advisor, cls.z1, Status.RESOLVED, "Opened until 20:00.")
            services.change_status(cls.advisor, cls.z2, Status.REJECTED, "Marks are correct.")
        with at(5):
            services.respond(cls.advisor, cls.a1, "Looking into it.")


class StaffSortTests(CompleteTestCase):
    def setUp(self):
        self.client.force_login(self.advisor)

    def test_every_sort_option(self):
        a1, z1, a2, z2 = (c.reference for c in (self.a1, self.z1, self.a2, self.z2))
        expected = {
            "": [a1, z2, z1, a2],  # latest activity: a1 (day 5), then the day-4 status changes
            "activity": [a1, z2, z1, a2],
            "newest": [z2, a2, z1, a1],
            "oldest": [a1, z1, a2, z2],
            # Received, Under Review, Resolved, Rejected (the workflow order)
            "status": [a2, a1, z1, z2],
            # Test Academic (a1, z2 by latest activity), then Test Other (z1, a2)
            "category": [a1, z2, z1, a2],
            "cohort": [a1, z2, z1, a2],  # one cohort: latest activity breaks the tie
            "nonsense": [a1, z2, z1, a2],
        }
        for sort, order in expected.items():
            with self.subTest(sort=sort):
                self.assertEqual(refs(self.client.get(ADVISOR_LIST, {"sort": sort})), order)

    def test_super_admin_cohort_sort(self):
        self.client.force_login(self.admin)
        response = self.client.get(ADMIN_LIST, {"sort": "cohort"})
        # Fall 2024 before Spring 2025; within Fall 2024, latest activity first.
        self.assertEqual(refs(response)[-1], self.o1.reference)
        self.assertEqual(refs(response)[0], self.a1.reference)
        labels = [label for _, label in response.context["filters"].fields["sort"].choices]
        self.assertEqual(labels, ["Latest activity", "Newest", "Oldest", "Status", "Category", "Cohort"])

    def test_sort_survives_pagination_and_filters(self):
        for i in range(PAGE_SIZE + 1):
            with at(6, i):
                submit(self.ali, self.categories["academic"], title=f"Bulk {i}")
        response = self.client.get(ADVISOR_LIST, {"sort": "oldest", "category": self.categories["academic"].pk})
        self.assertEqual(refs(response)[0], self.a1.reference)
        self.assertContains(response, f'href="?category={self.categories["academic"].pk}&amp;sort=oldest&amp;page=2"')
        second = self.client.get(ADVISOR_LIST, {"sort": "oldest", "category": self.categories["academic"].pk, "page": 2})
        self.assertEqual(len(refs(second)), 3)  # 23 academic complaints in the cohort

    def test_query_count_does_not_grow_with_rows(self):
        with CaptureQueriesContext(connection) as before:
            self.client.get(ADVISOR_LIST, {"sort": "category"})
        for i in range(8):
            with at(7, i):
                submit(self.zara, self.categories["other"], title=f"More {i}")
        with CaptureQueriesContext(connection) as after:
            self.client.get(ADVISOR_LIST, {"sort": "category"})
        self.assertEqual(len(after), len(before))

    def test_sorting_never_widens_the_list(self):
        for sort in ("cohort", "oldest", "status"):
            self.assertNotIn(self.o1.reference, refs(self.client.get(ADVISOR_LIST, {"sort": sort})))


class StudentSortTests(CompleteTestCase):
    def setUp(self):
        self.client.force_login(self.ali)

    def test_sort_options_and_default(self):
        page = self.client.get(STUDENT_LIST)
        self.assertEqual(refs(page), [self.a1.reference, self.a2.reference])  # latest activity
        self.assertEqual(refs(self.client.get(STUDENT_LIST, {"sort": "newest"})), [self.a2.reference, self.a1.reference])
        self.assertEqual(refs(self.client.get(STUDENT_LIST, {"sort": "oldest"})), [self.a1.reference, self.a2.reference])
        self.assertEqual(refs(self.client.get(STUDENT_LIST, {"sort": "status"})), [self.a2.reference, self.a1.reference])
        self.assertEqual(refs(self.client.get(STUDENT_LIST, {"sort": "category"})), [self.a1.reference, self.a2.reference])
        self.assertEqual(refs(self.client.get(STUDENT_LIST, {"sort": "cohort"})), [self.a1.reference, self.a2.reference])
        self.assertEqual(page.context["sort"], "activity")
        self.assertNotIn("cohort", [value for value, _ in page.context["sorts"]])

    def test_only_own_complaints(self):
        for sort in ("activity", "oldest", "status"):
            self.assertEqual(set(refs(self.client.get(STUDENT_LIST, {"sort": sort}))), {self.a1.reference, self.a2.reference})

    def test_sort_and_status_survive_pagination(self):
        for i in range(10):
            with at(6, i):
                submit(self.ali, self.categories["other"], title=f"Bulk {i}")
        response = self.client.get(STUDENT_LIST, {"status": Status.RECEIVED, "sort": "oldest"})
        self.assertEqual(refs(response)[0], self.a2.reference)
        self.assertContains(response, 'href="?status=received&amp;sort=oldest&amp;page=2"')
        self.assertContains(response, f'href="{STUDENT_LIST}?status=resolved&amp;sort=oldest"')  # status links keep the sort
        self.assertContains(response, '<option value="oldest" selected>')


class GoToReferenceTests(CompleteTestCase):
    def test_found_in_both_workspaces(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_complaint_go"), {"ref": f"  {self.z1.reference.lower()} "})
        self.assertRedirects(response, reverse("advisor_complaint_detail", args=[self.z1.reference]))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("super_admin_complaint_go"), {"ref": self.o1.reference})
        self.assertRedirects(response, reverse("super_admin_complaint_detail", args=[self.o1.reference]))

    def test_other_cohorts_are_not_found(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_complaint_go"), {"ref": self.o1.reference}, follow=True)
        self.assertRedirects(response, ADVISOR_LIST)
        self.assertContains(response, f"No complaint with the reference {self.o1.reference} was found in your complaints.")

    def test_unknown_empty_and_odd_input_never_fail(self):
        self.client.force_login(self.advisor)
        for value in ("CMP-2099-99999", "", "   ", "<script>", "x" * 500):
            with self.subTest(value=value[:20]):
                response = self.client.get(reverse("advisor_complaint_go"), {"ref": value})
                self.assertRedirects(response, ADVISOR_LIST)
                self.assertTrue(messages_of(response))
        self.assertRedirects(self.client.get(reverse("advisor_complaint_go")), ADVISOR_LIST)

    def test_role_required(self):
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get(reverse("advisor_complaint_go"), {"ref": self.a1.reference}).status_code, 403)
        self.assertEqual(self.client.get(reverse("super_admin_complaint_go"), {"ref": self.a1.reference}).status_code, 403)

    def test_form_is_on_both_lists(self):
        self.client.force_login(self.advisor)
        self.assertContains(self.client.get(ADVISOR_LIST), f'action="{reverse("advisor_complaint_go")}"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(ADMIN_LIST), f'action="{reverse("super_admin_complaint_go")}"')


class TrieSearchTests(CompleteTestCase):
    def test_names_surnames_and_sap_ids_by_prefix(self):
        self.client.force_login(self.advisor)
        cases = {
            "ali": {self.a1.reference, self.a2.reference},
            "ALI KH": {self.a1.reference, self.a2.reference},
            "khan": {self.a1.reference, self.a2.reference},  # a surname, via its own trie entry
            "ahm": {self.z1.reference, self.z2.reference},
            "8765": {self.z1.reference, self.z2.reference},
            "12345678": {self.a1.reference, self.a2.reference},
            "omar": set(),  # Omar's complaint is in another cohort
            "2222": set(),
            "han": set(),  # a prefix search, not a substring search
        }
        for q, expected in cases.items():
            with self.subTest(q=q):
                self.assertEqual(set(refs(self.client.get(ADVISOR_LIST, {"q": q}))), expected)

    def test_reference_and_title_search_still_work(self):
        self.client.force_login(self.admin)
        self.assertEqual(refs(self.client.get(ADMIN_LIST, {"q": self.o1.reference.split("-")[-1]})), [self.o1.reference])
        self.assertEqual(refs(self.client.get(ADMIN_LIST, {"q": "cooler"})), [self.a2.reference])
        self.assertEqual(set(refs(self.client.get(ADMIN_LIST, {"q": "omar f"}))), {self.o1.reference})

    def test_trie_holds_only_visible_students(self):
        trie = ordering.student_trie(Complaint.objects.filter(pk__in=[self.a1.pk]))
        self.assertEqual(trie.starts_with("ali"), [self.ali.pk])
        self.assertEqual(trie.starts_with("zara"), [])


class NextComplaintTests(CompleteTestCase):
    def setUp(self):
        self.client.force_login(self.advisor)

    def test_opens_the_oldest_waiting_complaint(self):
        # Waiting in the advisor's cohort: a1 (Under Review, day 0) and a2 (Received, day 2).
        response = self.client.get(reverse("advisor_complaint_next"))
        self.assertRedirects(response, reverse("advisor_complaint_detail", args=[self.a1.reference]))
        services.change_status(self.advisor, self.a1, Status.RESOLVED, "Fixed.")
        response = self.client.get(reverse("advisor_complaint_next"))
        self.assertRedirects(response, reverse("advisor_complaint_detail", args=[self.a2.reference]))

    def test_all_caught_up(self):
        for complaint in (self.a1, self.a2):
            services.change_status(self.advisor, complaint, Status.REJECTED, "Not in scope.")
        response = self.client.get(reverse("advisor_complaint_next"), follow=True)
        self.assertRedirects(response, ADVISOR_LIST)
        self.assertContains(response, "All caught up")

    def test_other_cohorts_are_never_next(self):
        older = make_student("33334444@student.uol.edu.pk", academics=self.academics, cohort=self.away, full_name="Early Bird")
        with at(-10):
            early = submit(older, self.categories["academic"], title="Earliest of all")
        self.assertEqual(ordering.next_waiting(Complaint.objects.all()).pk, early.pk)
        response = self.client.get(reverse("advisor_complaint_next"))
        self.assertRedirects(response, reverse("advisor_complaint_detail", args=[self.a1.reference]))

    def test_button_only_for_advisors_with_cohorts(self):
        self.assertContains(self.client.get(ADVISOR_LIST), f'href="{reverse("advisor_complaint_next")}"')
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get(ADMIN_LIST), "Next complaint")
        self.client.force_login(make_advisor("lonely@uol.edu.pk"))
        self.assertNotContains(self.client.get(ADVISOR_LIST), "Next complaint")


class StudentHomeTests(CompleteTestCase):
    def test_latest_staff_updates_newest_first(self):
        self.client.force_login(self.zara)
        response = self.client.get(reverse("student_home"))
        updates = response.context["updates"]
        # Zara: z1 resolved and z2 rejected (both day 4, z2 recorded later).
        self.assertEqual([u.headline for u in updates],
                         [f"{self.z2.reference} is now Rejected.", f"{self.z1.reference} is now Resolved."])
        self.assertEqual([u.tone for u in updates], ["rejected", "resolved"])
        self.assertEqual([u.label for u in updates], ["Status changed to Rejected", "Status changed to Resolved"])
        self.assertContains(response, "Status changed to Rejected")
        self.assertContains(response, 'href="%s"' % reverse("student_complaint_detail", args=[self.z1.reference]))
        self.assertEqual(response.context["summary"].lead, f"{self.z2.reference} is now Rejected.")
        self.assertEqual(response.context["summary"].rest, "You have 1 other update.")

    def test_new_badge_follows_the_unread_notification(self):
        self.client.force_login(self.ali)
        updates = self.client.get(reverse("student_home")).context["updates"]
        self.assertEqual([u.headline for u in updates],
                         [f"New response on {self.a1.reference}.", f"{self.a1.reference} is now Under Review."])
        self.assertTrue(all(u.is_new for u in updates))
        self.assertEqual(updates[0].status_label, "Under Review")  # a response shows the current status
        newest = Notification.objects.filter(recipient=self.ali).order_by("-created_at", "-id").first()
        notification_services.mark_read(self.ali, newest.pk)
        response = self.client.get(reverse("student_home"))
        self.assertEqual([u.is_new for u in response.context["updates"]], [False, True])
        self.assertContains(response, '<span class="sa-flag sa-flag--new">New</span>', count=1)

    def test_at_most_five_and_only_own(self):
        for i in range(4):
            with at(8, i):
                services.respond(self.advisor, self.a2, f"Update {i}")
        self.client.force_login(self.ali)
        updates = self.client.get(reverse("student_home")).context["updates"]
        self.assertEqual(len(updates), 5)
        self.assertEqual(updates[0].headline, f"New response on {self.a2.reference}.")
        self.assertTrue(all(u.reference in (self.a1.reference, self.a2.reference) for u in updates))

    def test_student_actions_are_not_updates_and_empty_state(self):
        newcomer = make_student("55556666@student.uol.edu.pk", academics=self.academics, full_name="New Comer")
        complaint = submit(newcomer, self.categories["other"])
        services.add_further_information(newcomer, complaint, "More details.")
        self.client.force_login(newcomer)
        response = self.client.get(reverse("student_home"))
        self.assertEqual(response.context["updates"], [])
        self.assertContains(response, "No updates yet.")
        self.assertContains(response, "Nothing needs your attention today.")


class AdvisorOverviewTests(CompleteTestCase):
    def test_counts_per_cohort(self):
        now = timezone.now()
        with mock.patch("django.utils.timezone.now", return_value=now - timedelta(days=2)):
            services.change_status(self.advisor, self.a2, Status.RESOLVED, "Refilled.")
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_home"))
        [card] = response.context["assignments"]
        # z1 was resolved on T0 + 4 days (long ago), a2 two days ago; a1 is still open.
        self.assertEqual(card.counts, {"open": 1, "resolved_recently": 1, "total": 4})
        self.assertContains(response, "Resolved 7d")

    def test_cohort_without_complaints_and_other_cohorts(self):
        empty = cohort(self.academics, section="other_section")
        advisor = make_advisor("two@uol.edu.pk", cohorts=[self.home, empty])
        self.client.force_login(advisor)
        cards = {cohort_value(a.batch_id, a.semester_id, a.section_id): a.counts
                 for a in self.client.get(reverse("advisor_home")).context["assignments"]}
        self.assertEqual(cards[cohort_value(*(e.pk for e in empty))], {"open": 0, "resolved_recently": 0, "total": 0})
        self.assertEqual(cards[cohort_value(*(e.pk for e in self.home))]["total"], 4)  # o1 is not counted

    def test_stale_wording_is_gone(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_home"))
        self.assertNotContains(response, "as each part of the portal opens")
        self.assertContains(response, "View complaints")
