"""Section Issues: raising, support, advisor actions, visibility, notifications, navigation and search."""

import re
import threading
from io import StringIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from academics.models import Batch, Section, Semester
from accounts import representation as rep
from accounts.models import CohortRepresentation
from accounts.representation import Cohort
from accounts.tests.helpers import cohort, make_academics, make_advisor, make_student, make_super_admin
from issues import services
from issues.models import CollectiveIssue, IssueEvent, ProtectedIssueError, Support
from issues.permissions import visible_issues
from notifications.models import Notification

Status = CollectiveIssue.Status
TITLE = "Projector in Room 204 is broken"
DESCRIPTION = "The projector has not worked for two weeks and lectures suffer."
RESPONSE = "PRIVATE-ADVISOR-RESPONSE maintenance has been told."
NOTE = "PRIVATE-RESOLUTION-NOTE the lamp was replaced."


class IssueTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.home = cohort(cls.academics)
        cls.away = cohort(cls.academics, section="other_section")
        cls.key = Cohort(*(entry.pk for entry in cls.home))
        cls.away_key = Cohort(*(entry.pk for entry in cls.away))
        cls.cr = make_student("10000001@student.uol.edu.pk", academics=cls.academics, full_name="Cara Rep")
        cls.gr = make_student("10000002@student.uol.edu.pk", academics=cls.academics, full_name="Gita Rep")
        cls.student = make_student("10000003@student.uol.edu.pk", academics=cls.academics, full_name="Sami Student")
        cls.spare = make_student("10000004@student.uol.edu.pk", academics=cls.academics, full_name="SupporterNameHidden")
        cls.outsider = make_student("10000005@student.uol.edu.pk", academics=cls.academics, cohort=cls.away, full_name="Omar Away")
        cls.outsider2 = make_student("10000006@student.uol.edu.pk", academics=cls.academics, cohort=cls.away, full_name="Ola Away")
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="First Advisor")
        cls.co_advisor = make_advisor("co@uol.edu.pk", cohorts=[cls.home], full_name="Second Advisor")
        cls.other_advisor = make_advisor("other@uol.edu.pk", cohorts=[cls.away], full_name="Other Advisor")
        cls.admin = make_super_admin()
        cls.period = rep.appoint_representatives(cls.admin, cls.key, cr=cls.cr, gr=cls.gr)

    def publish(self, user=None, title=TITLE, description=DESCRIPTION):
        return services.publish_issue(user or self.cr, title=title, description=description)

    def fresh(self, issue):
        return visible_issues(self.admin).get(pk=issue.pk)

    def page(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args))

    def deactivate(self, entry):
        type(entry).objects.filter(pk=entry.pk).update(is_active=False)


class RaisingTests(IssueTestCase):
    def test_current_cr_and_gr_can_raise_for_their_cohort(self):
        for user, post in ((self.cr, "cr"), (self.gr, "gr")):
            issue = self.publish(user)
            self.assertEqual(issue.raised_as, post)
            self.assertEqual(Cohort.of(issue), self.key)
            self.assertEqual(issue.status, Status.RECEIVED)

    def test_nobody_else_can_raise(self):
        for user in (self.student, self.outsider, self.advisor, self.admin):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                self.publish(user)
        self.assertFalse(CollectiveIssue.objects.exists())

    def test_unrepresented_cohort_cannot_raise_and_form_is_404(self):
        self.assertEqual(self.page(self.outsider, "student_issue_new").status_code, 404)

    def test_inactive_cohort_refuses_new_issues(self):
        self.deactivate(self.academics["section"])
        with self.assertRaises(ValidationError):
            self.publish()
        self.assertEqual(self.page(self.cr, "student_issue_new").status_code, 404)

    def test_validation_limits_after_trimming(self):
        for title, description in (("abcd", DESCRIPTION), ("   abcd   ", DESCRIPTION), ("x" * 121, DESCRIPTION),
                                   (TITLE, "x" * 19), (TITLE, " " * 30), (TITLE, "x" * 2001)):
            with self.subTest(title=title[:8], length=len(description)), self.assertRaises(ValidationError):
                self.publish(title=title, description=description)
        self.assertEqual(len(self.publish(title="x" * 120, description="y" * 2000).description), 2000)
        self.assertEqual(self.publish(title="  Five!  ", description="z" * 20).title, "Five!")

    def test_browser_line_endings_count_as_one_character(self):
        text = "\r\n".join(["x" * 99] * 20)  # 2019 characters as sent, 1999 as stored
        self.assertEqual(len(self.publish(description=text).description), 1999)

    def test_reference_format_is_unique(self):
        first, second = self.publish(), self.publish(self.gr)
        self.assertRegex(first.reference, r"^CI-\d{4}-\d{5}$")
        self.assertNotEqual(first.reference, second.reference)

    def test_review_then_publish_flow(self):
        self.client.force_login(self.cr)
        url = reverse("student_issue_new")
        data = {"title": TITLE, "description": DESCRIPTION}
        review = self.client.post(url, {**data, "step": "review"})
        self.assertTemplateUsed(review, "issues/review.html")
        self.assertFalse(CollectiveIssue.objects.exists())  # no drafts
        unconfirmed = self.client.post(url, {**data, "step": "publish"})
        self.assertEqual(unconfirmed.status_code, 400)
        self.assertFalse(CollectiveIssue.objects.exists())
        published = self.client.post(url, {**data, "step": "publish", "confirm": "on"})
        issue = CollectiveIssue.objects.get()
        self.assertRedirects(published, reverse("student_issue_detail", args=[issue.reference]))

    def test_back_to_editing_keeps_the_text(self):
        self.client.force_login(self.cr)
        page = self.client.post(reverse("student_issue_new"), {"title": TITLE, "description": DESCRIPTION, "step": "edit"})
        self.assertContains(page, TITLE)
        self.assertContains(page, DESCRIPTION)

    def test_invalid_form_stays_on_the_form(self):
        self.client.force_login(self.cr)
        page = self.client.post(reverse("student_issue_new"), {"title": "abc", "description": "short", "step": "review"})
        self.assertEqual(page.status_code, 400)
        self.assertTemplateUsed(page, "issues/new.html")

    def test_duplicate_warning_renders_and_does_not_block(self):
        existing = self.publish()
        self.client.force_login(self.gr)
        url = reverse("student_issue_new")
        data = {"title": "Projector in Room 204 is broke", "description": DESCRIPTION}
        review = self.client.post(url, {**data, "step": "review"})
        self.assertContains(review, "Your section may already have this issue.")
        self.assertContains(review, existing.reference)
        self.client.post(url, {**data, "step": "publish", "confirm": "on"})
        self.assertEqual(CollectiveIssue.objects.count(), 2)

    def test_duplicate_warning_ignores_closed_issues_and_other_cohorts(self):
        closed = self.publish()
        services.send_response(self.advisor, closed, RESPONSE)
        rep.appoint_representatives(self.admin, self.away_key, cr=self.outsider, gr=self.outsider2)
        self.publish(self.outsider)
        self.assertEqual(services.similar_open_issues(self.period, TITLE), [])

    def test_published_issues_cannot_be_edited_or_deleted(self):
        issue = self.publish()
        issue.title = "A changed title"
        with self.assertRaises(ProtectedIssueError):
            issue.save()
        with self.assertRaises(ProtectedIssueError):
            issue.delete()
        with self.assertRaises(ProtectedIssueError):
            CollectiveIssue.objects.filter(pk=issue.pk).update(title="Changed")
        with self.assertRaises(ProtectedIssueError):
            CollectiveIssue.objects.filter(pk=issue.pk).delete()

    def test_no_edit_or_delete_routes_exist(self):
        from issues import urls
        names = [p.name for group in (urls.student_patterns, urls.advisor_patterns, urls.super_admin_patterns) for p in group]
        self.assertFalse([name for name in names if "edit" in name or "delete" in name or "reject" in name or "reopen" in name])


class SupportTests(IssueTestCase):
    def test_support_once_only(self):
        issue = self.publish()
        self.assertTrue(services.support_issue(self.student, issue))
        self.assertFalse(services.support_issue(self.student, issue))
        self.assertEqual(self.fresh(issue).support_total, 1)

    def test_database_refuses_a_second_support(self):
        issue = self.publish()
        Support.objects.create(issue=issue, student=self.student)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Support.objects.bulk_create([Support(issue=issue, student=self.student)])

    def test_support_cannot_be_withdrawn(self):
        issue = self.publish()
        services.support_issue(self.student, issue)
        row = Support.objects.get()
        with self.assertRaises(ProtectedIssueError):
            row.delete()
        with self.assertRaises(ProtectedIssueError):
            Support.objects.all().delete()

    def test_cr_and_gr_can_support_even_their_own_issue(self):
        issue = self.publish()
        self.assertTrue(services.support_issue(self.cr, issue))
        self.assertTrue(services.support_issue(self.gr, issue))

    def test_other_cohorts_advisors_and_admin_cannot_support(self):
        issue = self.publish()
        for user in (self.outsider, self.advisor, self.admin):
            with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                services.support_issue(user, issue)

    def test_support_route_is_404_for_other_cohorts_and_staff_are_refused(self):
        issue = self.publish()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(reverse("student_issue_support", args=[issue.reference])).status_code, 404)
        for user in (self.advisor, self.admin):
            self.client.force_login(user)
            self.assertNotEqual(self.client.post(reverse("student_issue_support", args=[issue.reference])).status_code, 200)
        self.assertFalse(Support.objects.exists())

    def test_inactive_cohort_refuses_support_and_keeps_the_count(self):
        issue = self.publish()
        services.support_issue(self.student, issue)
        self.deactivate(self.academics["semester"])
        with self.assertRaisesMessage(ValidationError, services.SUPPORT_CLOSED):
            services.support_issue(self.spare, issue)
        self.assertEqual(self.fresh(issue).support_total, 1)

    def test_closed_support_refuses_and_count_freezes(self):
        issue = self.publish()
        services.support_issue(self.student, issue)
        services.send_response(self.advisor, issue, RESPONSE)
        with self.assertRaisesMessage(ValidationError, services.SUPPORT_CLOSED):
            services.support_issue(self.spare, issue)
        self.assertEqual(self.fresh(issue).support_total, 1)

    def test_supporter_identities_never_in_any_page(self):
        issue = self.publish()
        services.support_issue(self.spare, issue)
        pages = [(self.student, "student_issue_detail"), (self.cr, "student_issue_detail"),
                 (self.advisor, "advisor_issue_detail"), (self.admin, "super_admin_issue_detail")]
        for user, name in pages:
            with self.subTest(user=user.email):
                self.assertNotContains(self.page(user, name, issue.reference), "SupporterNameHidden")
        for user, name in ((self.cr, "student_section_issues"), (self.advisor, "advisor_issues"), (self.admin, "super_admin_issues")):
            with self.subTest(list=name):
                self.assertNotContains(self.page(user, name), "SupporterNameHidden")

    def test_support_from_home_returns_home(self):
        issue = self.publish()
        self.client.force_login(self.student)
        response = self.client.post(reverse("student_issue_support", args=[issue.reference]), {"from": "home"})
        self.assertRedirects(response, reverse("student_home"))
        self.assertContains(self.client.get(reverse("student_home")), "You supported this")


class AdvisorActionTests(IssueTestCase):
    def test_under_review_changes_status_only_and_keeps_support_open(self):
        issue = services.mark_under_review(self.advisor, self.publish())
        self.assertEqual(issue.status, Status.UNDER_REVIEW)
        self.assertIsNone(issue.first_response_at)
        self.assertTrue(services.support_issue(self.student, issue))

    def test_first_response_closes_support_and_never_changes_status(self):
        issue = self.publish()
        issue = services.send_response(self.advisor, issue, RESPONSE)
        self.assertEqual(issue.status, Status.RECEIVED)
        closed_at = issue.first_response_at
        self.assertIsNotNone(closed_at)
        issue = services.send_response(self.co_advisor, issue, "A second response.")
        self.assertEqual(issue.first_response_at, closed_at)
        self.assertEqual(IssueEvent.objects.filter(issue=issue, kind=IssueEvent.Kind.RESPONSE).count(), 2)

    def test_resolve_needs_a_note_closes_support_and_is_final(self):
        issue = self.publish()
        for note in ("", "   "):
            with self.subTest(note=note), self.assertRaises(ValidationError):
                services.resolve(self.advisor, issue, note)
        issue = services.resolve(self.advisor, issue, NOTE)
        self.assertEqual(issue.status, Status.RESOLVED)
        self.assertIsNotNone(issue.first_response_at)
        for action in (lambda: services.mark_under_review(self.advisor, issue),
                       lambda: services.send_response(self.advisor, issue, "More."),
                       lambda: services.resolve(self.advisor, issue, "Again.")):
            with self.assertRaisesMessage(ValidationError, services.ISSUE_FINAL):
                action()

    def test_resolved_row_cannot_be_changed(self):
        issue = services.resolve(self.advisor, self.publish(), NOTE)
        issue.status = Status.UNDER_REVIEW
        with self.assertRaises(ProtectedIssueError):
            issue.save()

    def test_database_refuses_resolved_without_a_note(self):
        issue = self.publish()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CollectiveIssue._base_manager.filter(pk=issue.pk).update(status="resolved")

    def test_response_length_limit(self):
        with self.assertRaises(ValidationError):
            services.send_response(self.advisor, self.publish(), "x" * 1001)

    def test_only_advisors_of_the_exact_cohort_can_act(self):
        issue = self.publish()
        for user in (self.other_advisor, self.admin, self.cr, self.student):
            for action in (lambda: services.mark_under_review(user, issue),
                           lambda: services.send_response(user, issue, RESPONSE),
                           lambda: services.resolve(user, issue, NOTE)):
                with self.subTest(user=user.email), self.assertRaises(PermissionDenied):
                    action()

    def test_every_assigned_advisor_can_act(self):
        issue = services.mark_under_review(self.co_advisor, self.publish())
        services.resolve(self.advisor, issue, NOTE)

    def test_stale_status_is_refused(self):
        issue = self.publish()
        services.mark_under_review(self.advisor, issue)
        with self.assertRaisesMessage(ValidationError, services.STALE_STATUS):
            services.resolve(self.co_advisor, issue, NOTE, expected_status=Status.RECEIVED)

    def test_inactive_cohort_still_allows_every_advisor_action(self):
        issue = self.publish()
        self.deactivate(self.academics["batch"])
        issue = services.mark_under_review(self.advisor, issue)
        issue = services.send_response(self.advisor, issue, RESPONSE)
        self.assertEqual(services.resolve(self.advisor, issue, NOTE).status, Status.RESOLVED)

    def test_action_routes(self):
        issue = self.publish()
        self.client.force_login(self.advisor)
        ref = issue.reference
        self.client.post(reverse("advisor_issue_review", args=[ref]), {"expected_status": "received"})
        self.assertEqual(self.fresh(issue).status, Status.UNDER_REVIEW)
        self.assertEqual(self.client.post(reverse("advisor_issue_respond", args=[ref]), {"response": ""}).status_code, 400)
        self.client.post(reverse("advisor_issue_respond", args=[ref]), {"response": RESPONSE})
        self.assertIsNotNone(self.fresh(issue).first_response_at)
        self.assertEqual(self.client.post(reverse("advisor_issue_resolve", args=[ref]), {"note": ""}).status_code, 400)
        self.client.post(reverse("advisor_issue_resolve", args=[ref]), {"note": NOTE, "expected_status": "under_review"})
        self.assertEqual(self.fresh(issue).status, Status.RESOLVED)

    def test_action_routes_are_post_only_and_404_for_other_advisors(self):
        issue = self.publish()
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(reverse("advisor_issue_resolve", args=[issue.reference])).status_code, 405)
        self.client.force_login(self.other_advisor)
        for name in ("advisor_issue_review", "advisor_issue_respond", "advisor_issue_resolve"):
            self.assertEqual(self.client.post(reverse(name, args=[issue.reference]), {"response": "x", "note": "x"}).status_code, 404)
        self.assertEqual(self.fresh(issue).status, Status.RECEIVED)


class VisibilityTests(IssueTestCase):
    def responded(self):
        issue = self.publish()
        services.send_response(self.advisor, issue, RESPONSE)
        return issue

    def test_non_representative_never_sees_responses_or_detailed_status(self):
        issue = services.resolve(self.advisor, self.responded(), NOTE)
        page = self.page(self.student, "student_issue_detail", issue.reference)
        self.assertContains(page, "Support closed")
        for hidden in (RESPONSE, NOTE, "Under Review", "Resolved"):
            self.assertNotContains(page, hidden)

    def test_noticeboard_shows_open_issues_newest_first_and_drops_closed_ones(self):
        first, second = self.publish(title="First open issue"), self.publish(title="Second open issue")
        closed = self.responded()
        home = self.page(self.student, "student_home").content.decode()
        self.assertLess(home.index(second.reference), home.index(first.reference))
        self.assertNotIn(closed.reference, home)

    def test_under_review_stays_on_the_noticeboard_without_its_status(self):
        issue = services.mark_under_review(self.advisor, self.publish())
        home = self.page(self.student, "student_home")
        self.assertContains(home, issue.reference)
        self.assertContains(home, "Open for support")

    def test_inactive_cohort_issue_leaves_the_noticeboard(self):
        issue = self.publish()
        self.deactivate(self.academics["section"])
        self.assertNotContains(self.page(self.student, "student_home"), issue.reference)

    def test_current_reps_see_full_history_including_predecessors(self):
        issue = self.responded()  # raised by the first CR
        rep.replace_representatives(self.admin, self.key, expected_period=self.period.pk, cr=self.spare)
        page = self.page(self.spare, "student_issue_detail", issue.reference)
        self.assertContains(page, RESPONSE)
        self.assertContains(self.page(self.spare, "student_section_issues"), issue.reference)

    def test_former_rep_loses_access_but_keeps_student_access(self):
        issue = self.responded()
        rep.replace_representatives(self.admin, self.key, expected_period=self.period.pk, cr=self.spare)
        self.assertEqual(self.page(self.cr, "student_section_issues").status_code, 404)
        page = self.page(self.cr, "student_issue_detail", issue.reference)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, RESPONSE)

    def test_section_list_is_404_for_ordinary_students(self):
        self.assertEqual(self.page(self.student, "student_section_issues").status_code, 404)

    def test_other_cohorts_get_404(self):
        issue = self.publish()
        self.assertEqual(self.page(self.outsider, "student_issue_detail", issue.reference).status_code, 404)
        self.assertEqual(self.page(self.other_advisor, "advisor_issue_detail", issue.reference).status_code, 404)
        self.assertNotContains(self.page(self.other_advisor, "advisor_issues"), issue.reference)

    def test_forged_cohort_filter_cannot_widen_the_list(self):
        issue = self.publish()
        self.client.force_login(self.other_advisor)
        response = self.client.get(reverse("advisor_issues"), {"cohort": self.key.key})
        self.assertNotContains(response, issue.reference)

    def test_advisor_sees_support_count_and_closed_time(self):
        issue = self.responded()
        page = self.page(self.advisor, "advisor_issue_detail", issue.reference)
        self.assertContains(page, RESPONSE)
        self.assertContains(page, "<dt>Closed</dt>")

    def test_filters(self):
        open_issue = self.publish(title="Open issue title")
        closed = self.responded()
        self.client.force_login(self.advisor)
        url = reverse("advisor_issues")
        by_support = self.client.get(url, {"support": "closed"})
        self.assertContains(by_support, closed.reference)
        self.assertNotContains(by_support, open_issue.reference)
        by_status = self.client.get(url, {"status": "resolved"})
        self.assertNotContains(by_status, open_issue.reference)
        by_query = self.client.get(url, {"q": "Open issue"})
        self.assertContains(by_query, open_issue.reference)
        self.assertNotContains(by_query, closed.reference)

    def test_super_admin_is_read_only(self):
        issue = self.responded()
        page = self.page(self.admin, "super_admin_issue_detail", issue.reference)
        self.assertContains(page, RESPONSE)
        self.assertContains(page, "Read-only oversight")
        self.assertNotContains(page, "<form method=\"post\" action=\"/advisor")
        self.assertContains(self.page(self.admin, "super_admin_issues"), issue.reference)
        self.client.force_login(self.admin)
        for name in ("advisor_issue_review", "advisor_issue_respond", "advisor_issue_resolve"):
            self.assertNotEqual(self.client.post(reverse(name, args=[issue.reference]), {"response": "x", "note": "x"}).status_code, 200)
        self.assertEqual(IssueEvent.objects.filter(issue=issue).count(), 2)

    def test_role_pages_refuse_other_roles(self):
        issue = self.publish()
        self.assertNotEqual(self.page(self.student, "advisor_issue_detail", issue.reference).status_code, 200)
        self.assertNotEqual(self.page(self.advisor, "super_admin_issue_detail", issue.reference).status_code, 200)


class NotificationTests(IssueTestCase):
    def recipients(self, event_type):
        return set(Notification.objects.filter(event_type=event_type).values_list("recipient_id", flat=True))

    def test_publish_notifies_the_cohort_except_the_author(self):
        issue = self.publish()
        self.assertEqual(self.recipients("issue.published"), {self.gr.pk, self.student.pk, self.spare.pk})
        notice = Notification.objects.filter(recipient=self.student).get()
        self.assertEqual(notice.title, f"New section issue: {TITLE}")
        self.assertEqual(notice.target_arg, issue.reference)

    def test_inactive_students_are_not_notified(self):
        type(self.spare).objects.filter(pk=self.spare.pk).update(is_active=False)
        self.publish()
        self.assertNotIn(self.spare.pk, self.recipients("issue.published"))

    def test_each_response_notifies_current_cr_and_gr_once(self):
        issue = self.publish()
        services.send_response(self.advisor, issue, RESPONSE)
        services.send_response(self.advisor, issue, "Another response.")
        self.assertEqual(Notification.objects.filter(event_type="issue.response").count(), 4)
        self.assertEqual(self.recipients("issue.response"), {self.cr.pk, self.gr.pk})

    def test_resolution_creates_one_notification_per_rep(self):
        services.resolve(self.advisor, self.publish(), NOTE)
        self.assertEqual(Notification.objects.filter(event_type="issue.resolved").count(), 2)
        self.assertFalse(Notification.objects.filter(event_type="issue.response").exists())

    def test_goes_to_the_reps_current_at_the_action(self):
        issue = self.publish()
        rep.replace_representatives(self.admin, self.key, expected_period=self.period.pk, cr=self.spare)
        services.send_response(self.advisor, issue, RESPONSE)
        self.assertEqual(self.recipients("issue.response"), {self.spare.pk, self.gr.pk})

    def test_under_review_does_not_notify(self):
        services.mark_under_review(self.advisor, self.publish())
        self.assertFalse(Notification.objects.exclude(event_type="issue.published").exists())

    def test_advisor_text_is_never_in_a_notification(self):
        services.resolve(self.advisor, services.send_response(self.advisor, self.publish(), RESPONSE), NOTE)
        for title, body in Notification.objects.values_list("title", "body"):
            self.assertNotIn("PRIVATE", title + body)

    def test_a_rolled_back_action_leaves_no_notification(self):
        issue = self.publish()
        with self.assertRaises(RuntimeError), transaction.atomic():
            services.send_response(self.advisor, issue, RESPONSE)
            raise RuntimeError
        self.assertFalse(Notification.objects.filter(event_type="issue.response").exists())


class NavigationAndSearchTests(IssueTestCase):
    def sidebar(self, user, home):
        html = self.page(user, home).content.decode()
        return html, html[html.index('<aside class="sa-sidebar"'):html.index("</aside>")]

    def test_section_issues_item_only_for_current_reps(self):
        _html, sidebar = self.sidebar(self.cr, "student_home")
        self.assertIn("Section issues", sidebar)
        _html, sidebar = self.sidebar(self.student, "student_home")
        self.assertNotIn("Section issues", sidebar)

    def test_phone_keeps_four_tabs_for_reps(self):
        html = self.page(self.cr, "student_home").content.decode()
        bottom = html[html.index('<nav class="sa-bottomnav"'):]
        bottom = bottom[:bottom.index("</nav>")]
        self.assertEqual(len(re.findall(r"<a href=", bottom)), 4)
        self.assertNotIn("Section issues", bottom)

    def test_new_menu_entry_only_for_active_reps(self):
        self.assertContains(self.page(self.gr, "student_home"), "Raise a section issue")
        self.assertNotContains(self.page(self.student, "student_home"), "Raise a section issue")
        self.deactivate(self.academics["section"])
        self.assertNotContains(self.page(self.gr, "student_home"), "Raise a section issue")

    def test_home_shows_rep_actions_only_to_reps(self):
        self.assertContains(self.page(self.cr, "student_home"), "Raise an issue")
        self.assertNotContains(self.page(self.student, "student_home"), "Raise an issue")

    def test_staff_navigation_links(self):
        self.assertIn(reverse("advisor_issues"), self.sidebar(self.advisor, "advisor_home")[1])
        self.assertIn(reverse("super_admin_issues"), self.sidebar(self.admin, "super_admin_home")[1])

    def search(self, user, text):
        self.client.force_login(user)
        return self.client.get(reverse("quick_search"), {"q": text})

    def test_quick_search_jumps_for_each_allowed_role(self):
        issue = self.publish()
        for user, name in ((self.student, "student_issue_detail"), (self.cr, "student_issue_detail"),
                           (self.advisor, "advisor_issue_detail"), (self.admin, "super_admin_issue_detail")):
            with self.subTest(user=user.email):
                self.assertRedirects(self.search(user, issue.reference.lower()), reverse(name, args=[issue.reference]))

    def test_quick_search_reveals_nothing_out_of_scope(self):
        issue = self.publish()
        for user in (self.outsider, self.other_advisor):
            with self.subTest(user=user.email):
                response = self.search(user, issue.reference)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, TITLE)
                self.assertContains(response, "No results.")


@override_settings(DEBUG=True, DEMO_STAFF_EMAILS=[])
class SeedDemoTests(TestCase):
    def test_seed_twice_covers_every_state_and_changes_nothing_the_second_time(self):
        call_command("seed_demo", stdout=StringIO())
        counts = (CollectiveIssue.objects.count(), Support.objects.count(), IssueEvent.objects.count(),
                  CohortRepresentation.objects.count(), Notification.objects.count())
        output = StringIO()
        call_command("seed_demo", stdout=output)
        self.assertIn("nothing to create", output.getvalue())
        self.assertEqual(counts, (CollectiveIssue.objects.count(), Support.objects.count(), IssueEvent.objects.count(),
                                  CohortRepresentation.objects.count(), Notification.objects.count()))

        issues = list(CollectiveIssue.objects.all())
        self.assertGreaterEqual(len(issues), 6)
        self.assertTrue([i for i in issues if i.status == Status.RECEIVED and i.first_response_at is None])
        self.assertTrue([i for i in issues if i.status == Status.UNDER_REVIEW and i.first_response_at is None])
        self.assertTrue([i for i in issues if i.status == Status.UNDER_REVIEW and i.first_response_at])
        self.assertTrue([i for i in issues if i.status == Status.RESOLVED])
        self.assertEqual(len({(i.batch_id, i.semester_id, i.section_id) for i in issues}), 2)

    def test_predecessor_issue_is_raised_by_a_former_representative(self):
        call_command("seed_demo", stdout=StringIO())
        current = {pk for pair in CohortRepresentation.objects.current().values_list("cr_id", "gr_id") for pk in pair}
        self.assertTrue([i for i in CollectiveIssue.objects.all() if i.raised_by_id not in current])

    def test_similar_pair_triggers_the_warning(self):
        call_command("seed_demo", stdout=StringIO())
        period = CohortRepresentation.objects.current().get(section__name="DEMO-A")
        self.assertEqual(len(services.similar_open_issues(period, "Projector in Room 204 needs fixing")), 2)


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentSupportTests(TransactionTestCase):
    """Real concurrent requests on separate database connections (MySQL)."""

    def setUp(self):
        batch, semester, section = Batch.objects.create(name="Fall 2024"), Semester.objects.create(number=4), Section.objects.create(name="A")
        home = (batch, semester, section)
        academics = {"batch": batch, "semester": semester, "section": section}
        self.cr = make_student("20000001@student.uol.edu.pk", academics=academics, full_name="Cara")
        self.gr = make_student("20000002@student.uol.edu.pk", academics=academics, full_name="Gita")
        self.student = make_student("20000003@student.uol.edu.pk", academics=academics, full_name="Sami")
        self.advisor = make_advisor(cohorts=[home])
        rep.appoint_representatives(make_super_admin(), Cohort(batch.pk, semester.pk, section.pk), cr=self.cr, gr=self.gr)
        self.issue = services.publish_issue(self.cr, title=TITLE, description=DESCRIPTION)

    def run_together(self, *actions):
        barrier, results = threading.Barrier(len(actions)), []

        def worker(action):
            try:
                barrier.wait(5)
                results.append(("ok", action()))
            except ValidationError as error:
                results.append(("refused", error))
            except Exception as error:  # reported by the assertion below
                results.append(("error", error))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(action,)) for action in actions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        self.assertEqual([r for r in results if r[0] == "error"], [])
        return results

    def test_double_submit_records_one_support(self):
        results = self.run_together(*[lambda: services.support_issue(self.student, self.issue)] * 6)
        self.assertEqual(sorted(value for _state, value in results), [False] * 5 + [True])
        self.assertEqual(Support.objects.filter(issue=self.issue, student=self.student).count(), 1)

    def test_support_against_the_closing_response_keeps_the_count_exact(self):
        results = self.run_together(lambda: services.support_issue(self.student, self.issue),
                                    lambda: services.send_response(self.advisor, self.issue, RESPONSE))
        supported = [r for r in results if r[0] == "ok" and r[1] is True]
        self.assertEqual(Support.objects.filter(issue=self.issue).count(), len(supported))
        self.assertIsNotNone(CollectiveIssue.objects.get(pk=self.issue.pk).first_response_at)
