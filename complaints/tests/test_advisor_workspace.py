"""Batch Advisor complaints workspace (Complaints Part 3; COMPLAINTS_PART3_SPEC.md section 11)."""

import re
import threading

from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from accounts.models import AdvisorAssignment
from complaints import services
from complaints.advisor_views import PAGE_SIZE, cohort_value
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent

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
LIST = reverse("advisor_complaints")


def detail(complaint, query=""):
    return reverse("advisor_complaint_detail", args=[complaint.reference]) + (f"?{query}" if query else "")


def action(name, complaint, query=""):
    return reverse(f"advisor_complaint_{name}", args=[complaint.reference]) + (f"?{query}" if query else "")


def between(html, start, end):
    begin = html.index(start)
    return html[begin:html.index(end, begin)]


class WorkspaceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        cls.categories = make_categories()
        cls.home = cohort(a)  # Fall 2024 · Semester 4 · Section A
        cls.student = make_student(academics=a, full_name="Ali Khan")  # SAP ID 12345678
        cls.classmate = make_student(OTHER_STUDENT_EMAIL, academics=a, full_name="Zara Ahmed")  # 87654321
        cls.other_batch_student = make_student(
            "22223333@student.uol.edu.pk", academics=a, cohort=cohort(a, batch="other_batch"), full_name="Omar Other"
        )
        cls.mine = submit(cls.student, cls.categories["academic"], title="Lab timetable clash")
        cls.classmates = submit(cls.classmate, cls.categories["other"], title="Library hours")
        cls.other_batch = submit(cls.other_batch_student, cls.categories["academic"], title="Other batch complaint")

        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.co_advisor = make_advisor("coadvisor@uol.edu.pk", cohorts=[cls.home], full_name="Mr. Bilal Shah")
        cls.other_batch_advisor = make_advisor(
            "otherbatch@uol.edu.pk", cohorts=[cohort(a, batch="other_batch")], full_name="Ms. Other Advisor"
        )
        cls.partial = make_advisor(
            "partial@uol.edu.pk",
            cohorts=[cohort(a, batch="other_batch"), cohort(a, semester="other_semester"), cohort(a, section="other_section")],
        )
        cls.admin = make_super_admin()

    def setUp(self):
        self.client.force_login(self.advisor)

    def html(self, url, **params):
        return self.client.get(url, params).content.decode()

    def list_refs(self, response):
        return [c.reference for c in response.context["page"].object_list]


class AccessTests(WorkspaceTestCase):
    def urls(self):
        return [
            ("get", LIST), ("get", detail(self.mine)),
            ("post", action("respond", self.mine)), ("post", action("status", self.mine)),
        ]

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        self.client.logout()
        for method, url in self.urls():
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_students_and_super_admins_are_refused(self):
        for user in (self.student, self.admin):
            self.client.force_login(user)
            for method, url in self.urls():
                with self.subTest(user=user.email, url=url):
                    self.assertEqual(getattr(self.client, method)(url, {"message": "x"}).status_code, 403)
        self.assertEqual(self.mine.events.count(), 1)

    def test_deactivated_advisor_loses_access(self):
        self.advisor.is_active = False
        self.advisor.save()
        self.assertEqual(self.client.get(LIST).status_code, 302)

    def test_advisor_without_assignments_sees_the_empty_state(self):
        self.client.force_login(make_advisor("new@uol.edu.pk"))
        response = self.client.get(LIST)
        self.assertContains(response, "No cohorts are assigned to you yet.")
        self.assertEqual(list(response.context["page"].object_list), [])

    def test_actions_require_post(self):
        for name in ("respond", "status"):
            self.assertEqual(self.client.get(action(name, self.mine)).status_code, 405)


class ExactCohortTests(WorkspaceTestCase):
    def test_list_shows_only_the_exactly_assigned_cohort(self):
        refs = self.list_refs(self.client.get(LIST))
        self.assertCountEqual(refs, [self.mine.reference, self.classmates.reference])
        self.assertNotIn(self.other_batch.reference, refs)

    def test_partial_matches_and_other_batches_see_nothing_of_this_cohort(self):
        # The partial advisor holds every part of the home cohort, never all three together.
        # (Its other-batch assignment is exactly the other-batch complaint's cohort.)
        self.client.force_login(self.partial)
        refs = self.list_refs(self.client.get(LIST))
        self.assertNotIn(self.mine.reference, refs)
        self.assertNotIn(self.classmates.reference, refs)
        self.assertEqual(self.client.get(detail(self.mine)).status_code, 404)
        self.client.force_login(self.other_batch_advisor)
        self.assertEqual(self.list_refs(self.client.get(LIST)), [self.other_batch.reference])

    def test_advisors_sharing_a_cohort_see_the_same_list(self):
        mine = sorted(self.list_refs(self.client.get(LIST)))
        self.client.force_login(self.co_advisor)
        self.assertEqual(sorted(self.list_refs(self.client.get(LIST))), mine)
        self.assertEqual(self.client.get(detail(self.mine)).status_code, 200)

    def test_out_of_cohort_reference_is_the_same_404_as_an_unknown_one(self):
        unknown = Complaint(reference="CMP-2026-99999")
        for name, out, missing in (
            ("detail", detail(self.other_batch), detail(unknown)),
            ("respond", action("respond", self.other_batch), action("respond", unknown)),
            ("status", action("status", self.other_batch), action("status", unknown)),
        ):
            with self.subTest(view=name):
                method = self.client.get if name == "detail" else self.client.post
                data = {} if name == "detail" else {"message": "x", "new_status": Status.REJECTED, "note": "x", "expected_status": Status.RECEIVED}
                out_response, missing_response = method(out, data), method(missing, data)
                self.assertEqual((out_response.status_code, missing_response.status_code), (404, 404))
                self.assertEqual(out_response.content, missing_response.content)
                self.assertNotIn(self.other_batch.title, out_response.content.decode())
        self.other_batch.refresh_from_db()
        self.assertEqual((self.other_batch.status, self.other_batch.events.count()), (Status.RECEIVED, 1))

    def test_cohort_filter_cannot_widen_the_list(self):
        a = self.academics
        forged = cohort_value(a["other_batch"].pk, a["semester"].pk, a["section"].pk)
        for value in (forged, "abc", "1.2", "999.999.999"):
            with self.subTest(value=value):
                refs = self.list_refs(self.client.get(LIST, {"cohort": value}))
                self.assertNotIn(self.other_batch.reference, refs)

    def test_search_cannot_reach_other_cohorts(self):
        for q in (self.other_batch.reference, "Omar", "22223333"):
            with self.subTest(q=q):
                self.assertEqual(self.list_refs(self.client.get(LIST, {"q": q})), [])


class SearchFilterSortTests(WorkspaceTestCase):
    def test_search_by_reference_name_and_sap_id(self):
        number = self.mine.reference.split("-")[-1]
        for q in (self.mine.reference.lower(), number, "ali kh", "12345678", "1234"):
            with self.subTest(q=q):
                self.assertEqual(self.list_refs(self.client.get(LIST, {"q": q})), [self.mine.reference])

    def test_status_filters_including_open(self):
        services.change_status(self.advisor, self.classmates, Status.RESOLVED, "Done.")
        self.assertEqual(self.list_refs(self.client.get(LIST, {"status": Status.RESOLVED})), [self.classmates.reference])
        self.assertEqual(self.list_refs(self.client.get(LIST, {"status": "open"})), [self.mine.reference])
        # P3-4: the default is All.
        self.assertEqual(len(self.list_refs(self.client.get(LIST))), 2)
        self.assertEqual(self.client.get(LIST).context["filters"]["status"].value(), None)

    def test_category_filter_and_choices(self):
        response = self.client.get(LIST, {"category": self.categories["other"].pk})
        self.assertEqual(self.list_refs(response), [self.classmates.reference])
        choices = [label for _, label in response.context["filters"].fields["category"].choices]
        self.assertEqual(choices, ["All categories", "Test Academic", "Test Other"])

    def test_cohort_filter_for_advisors_with_several_cohorts(self):
        AdvisorAssignment.objects.create(advisor=self.advisor, batch=self.academics["other_batch"],
                                         semester=self.academics["semester"], section=self.academics["section"])
        response = self.client.get(LIST)
        self.assertTrue(response.context["show_cohort_filter"])
        self.assertEqual(len(self.list_refs(response)), 3)
        value = cohort_value(*(entry.pk for entry in cohort(self.academics, batch="other_batch")))
        self.assertEqual(self.list_refs(self.client.get(LIST, {"cohort": value})), [self.other_batch.reference])
        self.assertFalse(self.client.get(LIST, {}).context["filters"].value("cohort"))

    def test_single_cohort_advisors_get_no_cohort_filter(self):
        self.assertFalse(self.client.get(LIST).context["show_cohort_filter"])

    def test_sort_by_latest_activity_or_newest(self):
        # mine was submitted first; a later response makes it the latest activity.
        services.respond(self.advisor, self.mine, "Looking into it.")
        self.assertEqual(self.list_refs(self.client.get(LIST))[0], self.mine.reference)
        self.assertEqual(self.list_refs(self.client.get(LIST, {"sort": "newest"}))[0], self.classmates.reference)

    def test_pagination_keeps_filters(self):
        academic = self.categories["academic"].pk
        for i in range(PAGE_SIZE + 2):
            submit(self.student, self.categories["academic"], title=f"Bulk {i}")
        # 23 Academic complaints in the cohort (22 new + "Lab timetable clash").
        response = self.client.get(LIST, {"q": "Ali", "category": academic})
        self.assertEqual(len(response.context["page"].object_list), PAGE_SIZE)
        self.assertContains(response, f'href="?q=Ali&amp;category={academic}&amp;page=2"')
        second = self.client.get(LIST, {"q": "Ali", "category": academic, "page": 2})
        self.assertEqual(len(second.context["page"].object_list), 3)

    def test_selected_case_links_keep_the_list_state(self):
        html = self.html(detail(self.mine), q="Ali", status="received")
        self.assertIn(f'href="{detail(self.mine)}?q=Ali&amp;status=received" aria-current="true"', html)
        self.assertIn(f'href="{LIST}?q=Ali&amp;status=received"', html)  # back link on phones
        self.assertIn(f'action="{action("respond", self.mine)}?q=Ali&amp;status=received"', html)

    def test_headline_uses_true_counts_only(self):
        services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW)
        self.assertContains(self.client.get(LIST), "Your cohorts have 2 open complaints: 1 received and 1 under review.")
        services.change_status(self.advisor, self.mine, Status.RESOLVED, "Done.")
        self.assertContains(self.client.get(LIST), "Your cohorts have 1 open complaint: 1 received.")
        services.change_status(self.advisor, self.classmates, Status.REJECTED, "Not ours.")
        self.assertContains(self.client.get(LIST), "There are no open complaints in your cohorts.")

    def test_no_matches_and_empty_states(self):
        self.assertContains(self.client.get(LIST, {"q": "nothing like this"}), "No complaints match these filters.")
        self.client.force_login(make_advisor("quiet@uol.edu.pk", cohorts=[cohort(self.academics, section="other_section")]))
        self.assertContains(self.client.get(LIST), "There are no complaints in your cohorts.")


class RespondTests(WorkspaceTestCase):
    def test_response_is_recorded_without_changing_status(self):
        response = self.client.post(action("respond", self.mine, "q=Lab"), {"message": "Which labs?"})
        self.assertRedirects(response, detail(self.mine, "q=Lab"), fetch_redirect_response=False)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.RECEIVED)
        event = self.mine.events.last()
        self.assertEqual((event.kind, event.actor, event.message), (Kind.RESPONSE, self.advisor, "Which labs?"))
        self.assertContains(self.client.get(detail(self.mine)), "Your response was sent. The status did not change.")

    def test_co_advisor_can_respond(self):
        self.client.force_login(self.co_advisor)
        self.client.post(action("respond", self.mine), {"message": "Also checking."})
        self.assertEqual(self.mine.events.last().actor, self.co_advisor)

    def test_empty_response_is_a_field_error(self):
        response = self.client.post(action("respond", self.mine), {"message": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Write a response.", status_code=400)
        self.assertContains(response, "data-error-focus", status_code=400)
        self.assertContains(response, 'aria-describedby="id_message-error id_message_helptext"', status_code=400)
        self.assertContains(response, 'id="id_message_helptext"', status_code=400)
        self.assertEqual(self.mine.events.count(), 1)


class StatusUpdateTests(WorkspaceTestCase):
    def offered(self, complaint):
        response = self.client.get(detail(complaint))
        return [value for value, _ in response.context["status_form"].fields["new_status"].choices], response

    def post_status(self, complaint, new_status, note="", expected=None):
        return self.client.post(action("status", complaint), {
            "new_status": new_status, "note": note, "expected_status": expected or complaint.status,
        })

    def test_only_allowed_transitions_are_offered(self):
        self.assertEqual(self.offered(self.mine)[0], [Status.UNDER_REVIEW, Status.RESOLVED, Status.REJECTED])
        services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW)
        self.assertEqual(self.offered(self.mine)[0], [Status.RESOLVED, Status.REJECTED])

    def test_closed_complaints_have_no_status_control(self):
        services.change_status(self.advisor, self.mine, Status.RESOLVED, "Done.")
        choices, response = self.offered(self.mine)
        self.assertEqual(choices, [])
        self.assertContains(response, "This complaint is resolved.")
        self.assertNotContains(response, 'name="new_status"')
        services.change_status(self.advisor, self.classmates, Status.REJECTED, "Not ours.")
        self.assertContains(self.client.get(detail(self.classmates)), "This complaint is rejected.")

    def test_valid_change_creates_an_event(self):
        response = self.post_status(self.mine, Status.UNDER_REVIEW, "Checking with the timetable office.")
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.UNDER_REVIEW)
        event = self.mine.events.last()
        self.assertEqual((event.kind, event.from_status, event.to_status, event.message),
                         (Kind.STATUS_CHANGED, Status.RECEIVED, Status.UNDER_REVIEW, "Checking with the timetable office."))

    def test_resolution_note_and_rejection_reason_are_required(self):
        for new_status, message in ((Status.RESOLVED, "A resolution note is required."), (Status.REJECTED, "A rejection reason is required.")):
            with self.subTest(new_status=new_status):
                response = self.post_status(self.mine, new_status, "   ")
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, message, status_code=400)
                self.assertContains(response, 'aria-describedby="id_note-error id_note_helptext"', status_code=400)
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.status, self.mine.events.count()), (Status.RECEIVED, 1))

    def test_missing_or_forged_choice_is_rejected(self):
        self.assertContains(self.post_status(self.mine, ""), "Choose the new status.", status_code=400)
        self.assertContains(self.post_status(self.mine, "overdue", "x"), "Choose one of the statuses offered.", status_code=400)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.RECEIVED)

    def test_forged_post_on_a_closed_complaint_is_refused_with_a_message(self):
        services.change_status(self.advisor, self.mine, Status.RESOLVED, "Done.")
        response = self.post_status(self.mine, Status.REJECTED, "Changing my mind.", expected=Status.RESOLVED)
        self.assertEqual(response.status_code, 400)  # Resolved offers no choices at all.
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.RESOLVED)

    def test_stale_page_is_refused_and_explained(self):
        # Advisor A opened the page at Received; a colleague moved it to Under Review first.
        services.change_status(self.co_advisor, self.mine, Status.UNDER_REVIEW)
        response = self.post_status(self.mine, Status.REJECTED, "Not a departmental matter.", expected=Status.RECEIVED)
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        page = self.client.get(detail(self.mine))
        self.assertContains(page, "This complaint is now Under Review: it changed after you opened it.")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.UNDER_REVIEW)
        self.assertEqual(self.mine.events.filter(kind=Kind.STATUS_CHANGED).count(), 1)

    def test_stale_transition_that_is_no_longer_allowed_is_explained_too(self):
        services.change_status(self.co_advisor, self.mine, Status.RESOLVED, "Done.")
        response = self.post_status(self.mine, Status.UNDER_REVIEW, "", expected=Status.RECEIVED)
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        self.assertContains(self.client.get(detail(self.mine)), "it changed after you opened it")


class ExpectedStatusServiceTests(WorkspaceTestCase):
    """P3-6: services.change_status(expected_status=...)."""

    def test_omitting_expected_status_keeps_existing_behaviour(self):
        services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW)
        self.assertEqual(services.change_status(self.advisor, self.mine, Status.RESOLVED, "Done.").status, Status.RESOLVED)

    def test_matching_expected_status_is_accepted(self):
        complaint = services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW, expected_status=Status.RECEIVED)
        self.assertEqual(complaint.status, Status.UNDER_REVIEW)

    def test_mismatched_expected_status_is_refused_without_changes(self):
        services.change_status(self.co_advisor, self.mine, Status.UNDER_REVIEW)
        with self.assertRaises(ValidationError) as caught:
            services.change_status(self.advisor, self.mine, Status.REJECTED, "Stale.", expected_status=Status.RECEIVED)
        self.assertEqual(caught.exception.code, "stale_status")
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.status, self.mine.events.count()), (Status.UNDER_REVIEW, 2))


class HistoryAndContextTests(WorkspaceTestCase):
    def test_history_is_newest_first_with_names_and_hidden_owner_changes(self):
        services.respond(self.advisor, self.mine, "First response.")
        services.change_status(self.co_advisor, self.mine, Status.RESOLVED, "Fixed.")
        services.mark_still_not_resolved(self.student, self.mine, "Still clashing.")
        services.request_cancellation(self.student, self.mine, "Sorted elsewhere.")
        services.assign_responsible(self.admin, self.mine, self.advisor)
        response = self.client.get(detail(self.mine))
        titles = [entry.title for entry in response.context["timeline"]]
        self.assertEqual(titles, [
            "Ali Khan asked to cancel this complaint",
            "Ali Khan marked this as still not resolved",
            "Status changed to Resolved",
            "Response from Dr. Ayesha Rahman (Batch Advisor)",
            "Ali Khan submitted this complaint",
        ])
        self.assertContains(response, "Mr. Bilal Shah (Batch Advisor)")
        self.assertContains(response, "Resolution note")
        self.assertNotContains(response, "Responsible")
        self.assertNotContains(response, "responsible_changed")

    def test_student_history_stays_oldest_first(self):
        services.respond(self.advisor, self.mine, "First response.")
        self.client.force_login(self.student)
        titles = [e.title for e in self.client.get(reverse("student_complaint_detail", args=[self.mine.reference])).context["timeline"]]
        self.assertEqual(titles, ["You submitted this complaint", "Response from Batch Advisor"])

    def test_context_panel(self):
        retired = make_advisor("retired@uol.edu.pk", cohorts=[self.home], full_name="Retired Advisor")
        retired.is_active = False
        retired.save()
        other_mine = submit(self.student, self.categories["other"], title="My second complaint")
        html = self.html(detail(self.mine))
        context = between(html, '<aside class="sa-ws-context"', "</aside>")
        self.assertIn("Ali Khan", context)
        self.assertIn("12345678", context)
        self.assertIn("Fall 2024 · Semester 4 · Section A", context)
        self.assertIn("Dr. Ayesha Rahman <span class=\"sa-muted\">(you)</span>", context)
        self.assertIn("Mr. Bilal Shah", context)
        self.assertNotIn("Retired Advisor", context)
        self.assertNotIn("Ms. Other Advisor", context)
        # P3-1 and DEC-305: no email, and not the student's other complaints.
        self.assertNotIn(self.student.email, html)
        self.assertNotIn(other_mine.title, between(html, '<section class="sa-ws-case"', "</section>\n</div>"))

    def test_only_the_cohort_at_submission_is_shown(self):
        profile = self.student.student_profile
        profile.section = self.academics["other_section"]
        profile.save()
        html = self.html(detail(self.mine))
        self.assertIn("Fall 2024 · Semester 4 · Section A", html)
        self.assertNotIn("Section B", html)  # P3-5: never the student's current cohort


class FlagsAndInvariantTests(WorkspaceTestCase):
    def test_factual_flags(self):
        services.request_cancellation(self.student, self.mine)
        services.change_status(self.advisor, self.classmates, Status.RESOLVED, "Done.")
        services.mark_still_not_resolved(self.classmate, self.classmates)
        rows = between(self.html(LIST), '<ul class="sa-ws-rows">', "</ul>")
        self.assertEqual(rows.count("Cancellation requested"), 1)
        self.assertEqual(rows.count("Reopened by student"), 1)

    def test_no_queue_owner_or_cancellation_controls(self):
        services.request_cancellation(self.student, self.mine)
        for url in (LIST, detail(self.mine)):
            html = self.html(url).lower()
            with self.subTest(url=url):
                for forbidden in ("waiting for you", "needs a response", "responsible", "approve", "cancel complaint", "decline"):
                    self.assertNotIn(forbidden, html)

    def test_respond_and_update_status_are_separate_forms(self):
        html = self.html(detail(self.mine))
        respond_form = between(html, f'action="{action("respond", self.mine)}', "</form>")
        status_form = between(html, f'action="{action("status", self.mine)}', "</form>")
        self.assertNotIn('name="new_status"', respond_form)
        self.assertNotIn('name="message"', status_form)
        self.assertIn('name="expected_status" value="received"', status_form)


class NavigationTests(WorkspaceTestCase):
    def test_complaints_navigation_links_and_stays_current(self):
        for url in (LIST, detail(self.mine)):
            with self.subTest(url=url):
                self.assertRegex(self.html(url), r'class="sa-rail-link" href="{}"[^>]*aria-current="page"'.format(re.escape(LIST)))

    def test_cohort_cards_link_to_the_filtered_workspace(self):
        a = self.academics
        value = cohort_value(a["batch"].pk, a["semester"].pk, a["section"].pk)
        html = self.html(reverse("advisor_home"))
        self.assertIn(f'href="{LIST}?cohort={value}"', html)
        self.assertCountEqual(self.list_refs(self.client.get(LIST, {"cohort": value})), [self.mine.reference, self.classmates.reference])


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentStatusUpdateTests(TransactionTestCase):
    """Two advisors of one cohort act on the same page state at once (MySQL)."""

    def test_only_one_stale_status_change_succeeds(self):
        a = make_academics()
        category = ComplaintCategory.objects.create(name="Race", position=99)
        student = make_student(academics=a)
        complaint = submit(student, category)
        advisors = [make_advisor(f"race{i}@uol.edu.pk", cohorts=[cohort(a)]) for i in range(2)]
        targets = [(Status.UNDER_REVIEW, ""), (Status.REJECTED, "Not ours.")]
        results, barrier = [], threading.Barrier(2)

        def worker(advisor, new_status, note):
            try:
                barrier.wait()
                services.change_status(advisor, complaint, new_status, note, expected_status=Status.RECEIVED)
                results.append("ok")
            except ValidationError as error:
                results.append(error.code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(adv, *target)) for adv, target in zip(advisors, targets)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(results, ["ok", "stale_status"])
        complaint.refresh_from_db()
        self.assertEqual(complaint.events.filter(kind=Kind.STATUS_CHANGED).count(), 1)
