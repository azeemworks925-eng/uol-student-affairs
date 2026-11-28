"""Notification pages, header entry point and permissions (Part 4 Stage 3)."""

import re

from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from accounts.tests.helpers import cohort, make_academics, make_advisor, make_student, make_super_admin
from complaints import services as complaint_services
from complaints.models import Complaint, ComplaintCategory
from complaints.tests.helpers import submit
from notifications import services
from notifications.context_processors import UnreadNotifications, notifications as notifications_context
from notifications.models import Notification

LIST = reverse("notifications")
READ_ALL = reverse("notifications_mark_all_read")
Status = Complaint.Status


def open_url(notification_or_pk):
    return reverse("notification_open", args=[getattr(notification_or_pk, "pk", notification_or_pk)])


class ViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.academics = make_academics()
        cls.category = ComplaintCategory.objects.create(name="Views", position=80)
        cls.student = make_student(academics=cls.academics, full_name="Ali Khan")
        cls.classmate = make_student("87654321@student.uol.edu.pk", academics=cls.academics, full_name="Zara Ahmed")
        cls.advisor = make_advisor(cohorts=[cohort(cls.academics)])
        cls.admin = make_super_admin()

    def setUp(self):
        self.complaint = submit(self.student, self.category, title="Lab timetable clash")
        complaint_services.respond(self.advisor, self.complaint, "We are checking.")
        self.notification = Notification.objects.get(recipient=self.student)
        self.client.force_login(self.student)


class AccessTests(ViewTestCase):
    def test_anonymous_visitors_are_sent_to_sign_in(self):
        self.client.logout()
        for method, url in (("get", LIST), ("post", open_url(self.notification)), ("post", READ_ALL)):
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("account_login")))
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)

    def test_inactive_users_lose_access_and_keep_their_notifications(self):
        self.student.is_active = False
        self.student.save()
        self.assertEqual(self.client.get(LIST).status_code, 302)
        self.assertEqual(self.client.post(open_url(self.notification)).status_code, 302)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)
        self.student.is_active = True
        self.student.save()
        self.client.force_login(self.student)
        self.assertContains(self.client.get(LIST), "We are checking.")

    def test_every_role_can_use_its_own_notifications_page(self):
        for user in (self.student, self.advisor, self.admin):
            self.client.force_login(user)
            with self.subTest(role=user.role):
                self.assertEqual(self.client.get(LIST).status_code, 200)

    def test_unregistered_students_are_sent_to_registration(self):
        self.client.force_login(make_student("99990000@student.uol.edu.pk"))
        self.assertRedirects(self.client.get(LIST), reverse("student_register"))

    def test_changes_require_post_and_csrf(self):
        for url in (open_url(self.notification), READ_ALL):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        for url in (open_url(self.notification), READ_ALL):
            with self.subTest(url=url):
                self.assertEqual(client.post(url).status_code, 403)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)

    def test_another_users_notification_is_a_plain_404(self):
        self.client.force_login(self.classmate)
        response = self.client.post(open_url(self.notification))
        missing = self.client.post(open_url(999999))
        self.assertEqual((response.status_code, missing.status_code), (404, 404))
        self.assertEqual(response.content, missing.content)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)
        self.assertNotContains(self.client.get(LIST), "We are checking.")
        # Marking all read only touches the classmate's own (none).
        self.client.post(READ_ALL)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)


class OpenTests(ViewTestCase):
    def test_opening_marks_read_and_goes_to_the_complaint(self):
        response = self.client.post(open_url(self.notification))
        detail = reverse("student_complaint_detail", args=[self.complaint.reference])
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], detail)
        self.notification.refresh_from_db()
        self.assertIsNotNone(self.notification.read_at)
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_a_tampered_destination_never_redirects_elsewhere(self):
        # Content cannot change through the ORM; simulate a row altered directly in the database.
        table = connection.ops.quote_name(Notification._meta.db_table)
        for url_name, arg in (("admin:index", ""), ("https://evil.example/x", ""), ("student_complaint_detail", "a/b")):
            with self.subTest(url_name=url_name), connection.cursor() as cursor:
                cursor.execute(f"UPDATE {table} SET target_url_name = %s, target_arg = %s, read_at = NULL WHERE id = %s",
                               [url_name, arg, self.notification.pk])
                response = self.client.post(open_url(self.notification), follow=False)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], LIST)
                self.assertContains(self.client.get(LIST), "no longer available")

    def test_a_notification_grants_no_access_to_the_linked_record(self):
        theirs = submit(self.classmate, self.category, title="Classmate private complaint")
        source = theirs.events.get()
        forged, _ = services.notify(self.student, event_type="complaint.response", source=source, title="Forged",
                                    target_url_name="student_complaint_detail", target_arg=theirs.reference)
        response = self.client.post(open_url(forged))
        self.assertEqual(response.status_code, 303)
        destination = self.client.get(response["Location"])
        self.assertEqual(destination.status_code, 404)
        self.assertNotContains(destination, "Classmate private complaint", status_code=404)


class ListTests(ViewTestCase):
    def test_list_shows_own_notifications_and_viewing_does_not_mark_read(self):
        response = self.client.get(LIST)
        self.assertContains(response, "You have 1 unread notification.")
        self.assertContains(response, f"New response on {self.complaint.reference}")
        self.assertContains(response, "Batch Advisor: We are checking.")
        self.assertContains(response, '<span class="visually-hidden">Unread: </span>', html=False)
        self.assertContains(response, "Mark all as read")
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)

    def test_mark_all_as_read(self):
        complaint_services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        response = self.client.post(READ_ALL, follow=True)
        self.assertRedirects(response, LIST)
        self.assertContains(response, "All caught up")
        self.assertContains(response, "No unread notifications.")
        self.assertNotContains(response, "Mark all as read")
        self.assertFalse(Notification.objects.filter(recipient=self.student, read_at__isnull=True).exists())

    def test_mark_all_read_returns_to_the_page_it_came_from(self):
        complaint_services.change_status(self.advisor, self.complaint, Status.UNDER_REVIEW)
        response = self.client.post(READ_ALL, {"next": reverse("student_voice")})
        self.assertRedirects(response, reverse("student_voice"), fetch_redirect_response=False)
        self.assertFalse(Notification.objects.filter(recipient=self.student, read_at__isnull=True).exists())

    def test_mark_all_read_never_redirects_off_site(self):
        for target in ("https://example.com/", "//example.com/x"):
            with self.subTest(target=target):
                response = self.client.post(READ_ALL, {"next": target})
                self.assertRedirects(response, LIST, fetch_redirect_response=False)

    def test_mark_all_read_from_the_bell_answers_json_and_touches_only_the_users_own(self):
        complaint_services.respond(self.advisor, submit(self.classmate, self.category, title="Projector broken"), "For the classmate")
        theirs = Notification.objects.filter(recipient=self.classmate, read_at__isnull=True).count()
        self.assertGreater(theirs, 0)
        response = self.client.post(READ_ALL, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread"], 0)
        self.assertFalse(Notification.objects.filter(recipient=self.student, read_at__isnull=True).exists())
        self.assertEqual(Notification.objects.filter(recipient=self.classmate, read_at__isnull=True).count(), theirs)

    def test_mark_all_read_needs_post_and_a_signed_in_user(self):
        self.assertEqual(self.client.get(READ_ALL).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(READ_ALL).status_code, 302)  # to sign-in

    def test_empty_states_by_role(self):
        self.client.force_login(self.classmate)
        self.assertContains(self.client.get(LIST), "Updates to your complaints")
        self.client.force_login(self.advisor)
        response = self.client.get(LIST)
        self.assertContains(response, "No notifications yet.")
        self.assertContains(response, "Notifications for your account will appear here.")

    def test_pagination(self):
        for i in range(21):
            complaint_services.respond(self.advisor, self.complaint, f"Response number {i}")
        first = self.client.get(LIST)
        self.assertEqual(len(first.context["page"].object_list), 20)
        self.assertContains(first, "Page 1 of 2")
        second = self.client.get(LIST, {"page": 2})
        self.assertEqual(len(second.context["page"].object_list), 2)
        self.assertContains(second, "We are checking.")  # the oldest


class HeaderTests(ViewTestCase):
    def header_links(self, html):
        bell = html[html.index('<details class="sa-pop sa-bell"'):]
        return re.findall(r'<summary class="sa-iconbtn"[^>]*aria-label="(Notifications[^"]+)"', bell[:bell.index("</summary>")])

    def test_every_role_has_the_entry_point_with_an_accurate_label(self):
        student_html = self.client.get(reverse("student_home")).content.decode()
        self.assertEqual(self.header_links(student_html), ["Notifications, 1 unread"])  # one bell, every viewport
        self.client.force_login(self.advisor)
        advisor_html = self.client.get(reverse("advisor_home")).content.decode()
        self.assertEqual(self.header_links(advisor_html), ["Notifications, none unread"])
        self.client.force_login(self.admin)
        admin_html = self.client.get(reverse("super_admin_home")).content.decode()
        self.assertEqual(self.header_links(admin_html), ["Notifications, none unread"])

    def test_badge_counts_and_caps(self):
        self.assertContains(self.client.get(reverse("student_home")), '<span class="sa-badge sa-badge--dot" aria-hidden="true" data-bell-badge>1</span>')
        for i in range(10):
            complaint_services.respond(self.advisor, self.complaint, f"More {i}")
        html = self.client.get(reverse("student_home")).content.decode()
        self.assertIn('<span class="sa-badge sa-badge--dot" aria-hidden="true" data-bell-badge>9+</span>', html)
        self.assertIn('aria-label="Notifications, 11 unread"', html)
        services.mark_all_read(self.student)
        self.assertNotIn('class="sa-badge', self.client.get(reverse("student_home")).content.decode())

    def test_entry_point_links_to_the_page_and_is_not_in_role_navigation(self):
        html = self.client.get(LIST).content.decode()
        self.assertIn('<a class="sa-bell-all" href="/notifications/">View all', html)
        sidebar = html[html.index('<aside class="sa-sidebar"'):html.index("</aside>")]
        self.assertNotIn("/notifications/", sidebar)  # moved from the sidebar to the bell
        bottom = html[html.index('<nav class="sa-bottomnav"'):]
        bottom = bottom[:bottom.index("</nav>")]
        self.assertNotIn("/notifications/", bottom)  # still exactly the four DEC-304 destinations

    def test_context_processor_is_lazy_and_only_for_active_signed_in_users(self):
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertEqual(notifications_context(request), {})
        self.student.is_active = False
        request.user = self.student
        self.assertEqual(notifications_context(request), {})
        self.student.is_active = True
        with self.assertNumQueries(0):
            unread = UnreadNotifications(self.student)
        with self.assertNumQueries(1):
            self.assertEqual(unread.count, 1)
            self.assertEqual(unread.display, "1")

    def test_sign_in_page_does_not_query_notifications(self):
        self.client.logout()
        response = self.client.get(reverse("account_login"))
        self.assertNotIn("sa_notifications", response.context)
