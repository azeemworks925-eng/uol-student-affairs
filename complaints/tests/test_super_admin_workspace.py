"""Super Admin complaints workspace and owner assignment (Complaints Part 4 Stage 1, spec section 3)."""

import re

from django.test import TestCase
from django.urls import reverse

from accounts.models import AdvisorAssignment
from complaints import services
from complaints.models import Complaint, ComplaintCategory, ComplaintEvent
from complaints.workspace import PAGE_SIZE, cohort_value

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
LIST = reverse("super_admin_complaints")


def detail(complaint, query=""):
    return reverse("super_admin_complaint_detail", args=[complaint.reference]) + (f"?{query}" if query else "")


def action(name, complaint, query=""):
    return reverse(f"super_admin_complaint_{name}", args=[complaint.reference]) + (f"?{query}" if query else "")


def between(html, start, end):
    begin = html.index(start)
    return html[begin:html.index(end, begin)]


class SuperAdminWorkspaceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = cls.academics = make_academics()
        cls.categories = make_categories()
        cls.home = cohort(a)  # Fall 2024 · Semester 4 · Section A
        cls.other = cohort(a, batch="other_batch")  # Spring 2025 · Semester 4 · Section A
        cls.student = make_student(academics=a, full_name="Ali Khan")  # SAP ID 12345678
        cls.other_student = make_student(OTHER_STUDENT_EMAIL, academics=a, cohort=cls.other, full_name="Zara Ahmed")
        cls.mine = submit(cls.student, cls.categories["academic"], title="Lab timetable clash")
        cls.theirs = submit(cls.other_student, cls.categories["other"], title="Library hours")
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.co_advisor = make_advisor("coadvisor@uol.edu.pk", cohorts=[cls.home], full_name="Mr. Bilal Shah")
        cls.other_advisor = make_advisor("otherbatch@uol.edu.pk", cohorts=[cls.other], full_name="Ms. Other Advisor")
        cls.admin = make_super_admin()
        cls.admin.full_name = "Head of Batch Advisors"
        cls.admin.save()
        cls.second_admin = make_super_admin("deputy@uol.edu.pk")

    def setUp(self):
        self.client.force_login(self.admin)

    def html(self, url, **params):
        return self.client.get(url, params).content.decode()

    def refs(self, response):
        return [c.reference for c in response.context["page"].object_list]

    def assign(self, complaint, owner, query=""):
        return self.client.post(action("owner", complaint, query), {"owner": owner.pk})


class AccessTests(SuperAdminWorkspaceTestCase):
    def urls(self):
        return [("get", LIST), ("get", detail(self.mine)), ("post", action("respond", self.mine)),
                ("post", action("status", self.mine)), ("post", action("owner", self.mine))]

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        self.client.logout()
        for method, url in self.urls():
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_students_and_batch_advisors_are_refused(self):
        for user in (self.student, self.advisor):
            self.client.force_login(user)
            for method, url in self.urls():
                with self.subTest(user=user.email, url=url):
                    self.assertEqual(getattr(self.client, method)(url, {"message": "x", "owner": self.advisor.pk}).status_code, 403)
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.responsible, self.mine.events.count()), (None, 1))

    def test_inactive_super_admin_loses_access(self):
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.client.get(LIST).status_code, 302)

    def test_actions_require_post(self):
        for name in ("respond", "status", "owner"):
            self.assertEqual(self.client.get(action(name, self.mine)).status_code, 405)

    def test_unknown_reference_is_404_on_every_route(self):
        unknown = Complaint(reference="CMP-2026-99999")
        self.assertEqual(self.client.get(detail(unknown)).status_code, 404)
        for name in ("respond", "status", "owner"):
            self.assertEqual(self.client.post(action(name, unknown), {"owner": self.advisor.pk}).status_code, 404)

    def test_navigation_links_and_stays_current(self):
        for url in (LIST, detail(self.mine)):
            with self.subTest(url=url):
                self.assertRegex(self.html(url), r'<a class="sa-nav-link" href="{}"[^>]*aria-current="page">'.format(re.escape(LIST)))


class ListTests(SuperAdminWorkspaceTestCase):
    def test_lists_every_complaint_department_wide(self):
        response = self.client.get(LIST)
        self.assertCountEqual(self.refs(response), [self.mine.reference, self.theirs.reference])
        self.assertContains(response, "The department has 2 open complaints: 2 received.")

    def test_rows_show_sap_id_cohort_category_owner_and_status(self):
        services.assign_responsible(self.admin, self.mine, self.advisor)
        rows = between(self.html(LIST), '<ul class="sa-collection"', "</ul>")
        for text in ("Ali Khan", "12345678", "Fall 2024 · Semester 4 · Section A", "Test Academic",
                     "Owner: Dr. Ayesha Rahman", "Unassigned", "Received", "Last activity"):
            self.assertIn(text, rows)

    def test_search_by_reference_title_name_and_sap_id(self):
        for q in (self.mine.reference, "timetable", "ali kh", "1234"):
            with self.subTest(q=q):
                self.assertEqual(self.refs(self.client.get(LIST, {"q": q})), [self.mine.reference])

    def test_cohort_filter_is_exact_and_offers_every_known_cohort(self):
        AdvisorAssignment.objects.create(advisor=self.advisor, batch=self.academics["batch"],
                                         semester=self.academics["semester"], section=self.academics["other_section"])
        response = self.client.get(LIST)
        labels = [label for _, label in response.context["filters"].fields["cohort"].choices]
        self.assertEqual(labels, ["All cohorts", "Fall 2024 · Semester 4 · Section A",
                                  "Fall 2024 · Semester 4 · Section B", "Spring 2025 · Semester 4 · Section A"])
        home = cohort_value(*(e.pk for e in self.home))
        self.assertEqual(self.refs(self.client.get(LIST, {"cohort": home})), [self.mine.reference])
        # A forged value is ignored rather than trusted.
        self.assertEqual(len(self.refs(self.client.get(LIST, {"cohort": "999.999.999"}))), 2)

    def test_empty_selected_cohort_is_told_apart_from_no_matches(self):
        AdvisorAssignment.objects.create(advisor=self.advisor, batch=self.academics["batch"],
                                         semester=self.academics["semester"], section=self.academics["other_section"])
        empty = cohort_value(self.academics["batch"].pk, self.academics["semester"].pk, self.academics["other_section"].pk)
        self.assertContains(self.client.get(LIST, {"cohort": empty}),
                            "No complaints have been submitted in Fall 2024 · Semester 4 · Section B.")
        self.assertContains(self.client.get(LIST, {"q": "nothing like this"}), "No complaints match these filters.")

    def test_status_filter_options_and_default(self):
        response = self.client.get(LIST)
        values = [value for value, _ in response.context["filters"].fields["status"].choices]
        self.assertEqual(values, ["", Status.RECEIVED, Status.UNDER_REVIEW, Status.RESOLVED, Status.REJECTED])
        services.change_status(self.advisor, self.mine, Status.RESOLVED, "Done.")
        self.assertEqual(self.refs(self.client.get(LIST, {"status": Status.RESOLVED})), [self.mine.reference])

    def test_category_filter_includes_inactive_categories_on_records(self):
        ComplaintCategory.objects.filter(pk=self.categories["other"].pk).update(is_active=False)
        response = self.client.get(LIST, {"category": self.categories["other"].pk})
        self.assertEqual(self.refs(response), [self.theirs.reference])

    def test_owner_filter(self):
        services.assign_responsible(self.admin, self.mine, self.advisor)
        services.assign_responsible(self.admin, self.theirs, self.admin)
        labels = [label for _, label in self.client.get(LIST).context["filters"].fields["owner"].choices]
        self.assertEqual(labels, ["Any owner", "Unassigned", "Dr. Ayesha Rahman (Batch Advisor)", "Head of Batch Advisors (Super Admin)"])
        self.assertEqual(self.refs(self.client.get(LIST, {"owner": self.advisor.pk})), [self.mine.reference])
        self.assertEqual(self.refs(self.client.get(LIST, {"owner": self.admin.pk})), [self.theirs.reference])
        submit(self.student, self.categories["academic"], title="Fresh")
        self.assertEqual(len(self.refs(self.client.get(LIST, {"owner": "unassigned"}))), 1)

    def test_sort_and_pagination_keep_state(self):
        for i in range(PAGE_SIZE + 1):
            submit(self.student, self.categories["academic"], title=f"Bulk {i}")
        response = self.client.get(LIST, {"q": "Bulk", "sort": "newest"})
        self.assertEqual(self.refs(response)[0], Complaint.objects.get(title=f"Bulk {PAGE_SIZE}").reference)
        self.assertContains(response, 'href="?q=Bulk&amp;sort=newest&amp;page=2"')
        self.assertEqual(len(self.client.get(LIST, {"q": "Bulk", "sort": "newest", "page": 2}).context["page"].object_list), 1)

    def test_case_links_and_redirects_keep_the_list_state(self):
        html = self.html(detail(self.mine), q="Ali", owner="unassigned")
        self.assertIn(f'href="{LIST}?q=Ali&amp;owner=unassigned"', html)  # Back to complaints
        self.assertIn(f'action="{action("owner", self.mine)}?q=Ali&amp;owner=unassigned"', html)
        response = self.assign(self.mine, self.advisor, "q=Ali&owner=unassigned")
        self.assertRedirects(response, detail(self.mine, "q=Ali&owner=unassigned"), fetch_redirect_response=False)

    def test_no_queue_or_priority_language(self):
        services.request_cancellation(self.student, self.mine)
        for url in (LIST, detail(self.mine)):
            html = self.html(url).lower()
            for forbidden in ("waiting for you", "needs a response", "overdue", "priority", "approve", "cancel complaint"):
                self.assertNotIn(forbidden, html)


class CaseTests(SuperAdminWorkspaceTestCase):
    def test_case_shows_original_context_and_full_staff_history(self):
        services.assign_responsible(self.admin, self.mine, self.advisor)
        services.respond(self.advisor, self.mine, "Looking into it.")
        services.assign_responsible(self.admin, self.mine, self.admin)
        response = self.client.get(detail(self.mine))
        titles = [entry.title for entry in response.context["timeline"]]
        self.assertEqual(titles, [
            "Head of Batch Advisors (Super Admin) took over this complaint",
            "Response from Dr. Ayesha Rahman (Batch Advisor)",
            "Responsible owner set to Dr. Ayesha Rahman (Batch Advisor)",
            "Ali Khan submitted this complaint",
        ])
        context = between(response.content.decode(), '<aside class="sa-detail-side"', "</aside>")
        for text in ("Ali Khan", "12345678", "Fall 2024 · Semester 4 · Section A", "Head of Batch Advisors (Super Admin)",
                     "Dr. Ayesha Rahman", "Mr. Bilal Shah"):
            self.assertIn(text, context)
        self.assertNotIn(self.student.email, response.content.decode())

    def test_unassigned_is_explicit_and_opening_does_not_assign(self):
        response = self.client.get(detail(self.mine))
        self.assertContains(response, "This complaint is <b>unassigned</b>")
        self.mine.refresh_from_db()
        self.assertIsNone(self.mine.responsible)
        self.assertEqual(self.mine.events.count(), 1)

    def test_super_admin_responds_and_changes_status_through_the_services(self):
        self.client.post(action("respond", self.mine), {"message": "We are on it."})
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.status, self.mine.events.last().kind), (Status.RECEIVED, Kind.RESPONSE))
        self.client.post(action("status", self.mine), {"new_status": Status.REJECTED, "note": "", "expected_status": Status.RECEIVED})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.RECEIVED)  # reason required
        self.client.post(action("status", self.mine), {"new_status": Status.UNDER_REVIEW, "note": "", "expected_status": Status.RECEIVED})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.UNDER_REVIEW)

    def test_stale_status_is_refused(self):
        services.change_status(self.advisor, self.mine, Status.UNDER_REVIEW)
        response = self.client.post(action("status", self.mine), {
            "new_status": Status.REJECTED, "note": "Stale.", "expected_status": Status.RECEIVED,
        })
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        self.assertContains(self.client.get(detail(self.mine)), "it changed after you opened it")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.UNDER_REVIEW)

    def test_original_description_and_category_are_untouched(self):
        original = (self.mine.description, self.mine.category_id)
        self.assign(self.mine, self.advisor)
        self.client.post(action("respond", self.mine), {"message": "Noted."})
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.description, self.mine.category_id), original)


class OwnerAssignmentTests(SuperAdminWorkspaceTestCase):
    def owner_choices(self, complaint):
        return [label for _, label in self.client.get(detail(complaint)).context["owner_form"].fields["owner"].choices]

    def test_choices_are_exact_cohort_advisors_and_taking_it_over(self):
        inactive = make_advisor("inactive@uol.edu.pk", cohorts=[self.home], full_name="Inactive Advisor")
        inactive.is_active = False
        inactive.save()
        self.assertEqual(self.owner_choices(self.mine), [
            "Choose a person", "Dr. Ayesha Rahman (Batch Advisor)", "Mr. Bilal Shah (Batch Advisor)",
            "Take it over yourself (Head of Batch Advisors)",
        ])

    def test_assigning_creates_one_event_and_shows_in_staff_history(self):
        response = self.assign(self.mine, self.advisor)
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.responsible, self.advisor)
        events = self.mine.events.filter(kind=Kind.RESPONSIBLE_CHANGED)
        self.assertEqual([(e.actor, e.responsible) for e in events], [(self.admin, self.advisor)])
        self.assertContains(self.client.get(detail(self.mine)), "Dr. Ayesha Rahman is now the responsible owner")

    def test_same_owner_is_a_no_op(self):
        self.assign(self.mine, self.advisor)
        response = self.assign(self.mine, self.advisor)
        self.assertRedirects(response, detail(self.mine), fetch_redirect_response=False)
        self.assertEqual(self.mine.events.filter(kind=Kind.RESPONSIBLE_CHANGED).count(), 1)
        self.assertContains(self.client.get(detail(self.mine)), "No change: Dr. Ayesha Rahman is already the responsible owner.")

    def test_reassign_and_take_over(self):
        self.assign(self.mine, self.advisor)
        self.assign(self.mine, self.co_advisor)
        self.assign(self.mine, self.admin)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.responsible, self.admin)
        owners = list(self.mine.events.filter(kind=Kind.RESPONSIBLE_CHANGED).values_list("responsible", flat=True))
        self.assertEqual(owners, [self.advisor.pk, self.co_advisor.pk, self.admin.pk])

    def test_ineligible_owners_are_rejected(self):
        # Wrong-cohort advisor, student and inactive advisor are ineligible (DEC-310). Another
        # active Super Admin is not offered either: the form offers taking it over yourself.
        inactive = make_advisor("inactive@uol.edu.pk", cohorts=[self.home])
        inactive.is_active = False
        inactive.save()
        for person in (self.other_advisor, self.student, inactive, self.second_admin):
            with self.subTest(person=person.email):
                response = self.assign(self.mine, person)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Choose one of the people offered.", status_code=400)
        self.assertEqual(self.client.post(action("owner", self.mine), {"owner": ""}).status_code, 400)
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.responsible, self.mine.events.count()), (None, 1))

    def test_service_rejects_ineligible_owners_too(self):
        from django.core.exceptions import ValidationError

        for person in (self.other_advisor, self.student):
            with self.subTest(person=person.email), self.assertRaises(ValidationError):
                services.assign_responsible(self.admin, self.mine, person)

    def test_owner_who_is_no_longer_eligible_is_labelled(self):
        services.assign_responsible(self.admin, self.mine, self.advisor)
        self.advisor.advisor_assignments.all().delete()
        self.assertContains(self.client.get(detail(self.mine)), "No longer eligible")


class OwnerDoesNotChangeAccessTests(SuperAdminWorkspaceTestCase):
    """DEC-310: the owner is for accountability; every advisor of the exact cohort keeps access."""

    def setUp(self):
        super().setUp()
        services.assign_responsible(self.admin, self.mine, self.advisor)

    def test_non_owner_advisor_keeps_visibility_and_actions(self):
        self.client.force_login(self.co_advisor)
        self.assertEqual(self.client.get(reverse("advisor_complaint_detail", args=[self.mine.reference])).status_code, 200)
        self.client.post(reverse("advisor_complaint_respond", args=[self.mine.reference]), {"message": "Also checking."})
        self.client.post(reverse("advisor_complaint_status", args=[self.mine.reference]),
                         {"new_status": Status.UNDER_REVIEW, "note": "", "expected_status": Status.RECEIVED})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Status.UNDER_REVIEW)
        self.assertEqual(self.mine.events.filter(actor=self.co_advisor).count(), 2)

    def test_owner_gains_nothing_outside_the_cohort(self):
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(reverse("advisor_complaint_detail", args=[self.theirs.reference])).status_code, 404)

    def test_advisor_workspace_is_unchanged(self):
        self.client.force_login(self.advisor)
        html = self.client.get(reverse("advisor_complaint_detail", args=[self.mine.reference])).content.decode()
        self.assertNotIn("Responsible", html)
        self.assertNotIn("took over", html)
        self.assertNotIn('name="owner"', html)
        titles = [e.title for e in self.client.get(reverse("advisor_complaint_detail", args=[self.mine.reference])).context["timeline"]]
        self.assertEqual(titles, ["Ali Khan submitted this complaint"])

    def test_students_never_see_the_owner(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_complaint_detail", args=[self.mine.reference]))
        html = response.content.decode()
        for hidden in ("Dr. Ayesha Rahman", "Responsible", "responsible owner", "took over", 'name="owner"'):
            self.assertNotIn(hidden, html)
        self.assertEqual([e.title for e in response.context["timeline"]], ["You submitted this complaint"])
        listing = self.client.get(reverse("student_complaints")).content.decode()
        self.assertNotIn("Dr. Ayesha Rahman", listing)


class EmptyDepartmentTests(TestCase):
    def test_no_complaints_state(self):
        self.client.force_login(make_super_admin())
        response = self.client.get(LIST)
        self.assertContains(response, "No complaints have been submitted yet.")
        self.assertEqual(list(response.context["page"].object_list), [])
