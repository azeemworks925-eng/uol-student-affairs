"""Polish v2 foundation (docs/POLISH_V2.md): the status colour map, the create-button rule, the
sign-in message, message copy, the component gallery and the no-JavaScript fallbacks."""

import ast
import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts import tones
from accounts.models import User
from accounts.navigation import CREATE_ACTIONS, create_actions, create_control
from accounts.representation import Cohort, appoint_representatives
from complaints.models import ComplaintStatus
from issues.models import CollectiveIssue
from meetings.models import Meeting
from voice.models import Submission

from .helpers import (GOOGLE_PROVIDERS, STUDENT_EMAIL, cohort, google_claims, google_sign_in, make_academics,
                      make_advisor, make_student, make_super_admin)

PROJECT = Path(settings.BASE_DIR)


class ToneMapTests(SimpleTestCase):
    def test_every_status_of_every_model_maps_to_a_tone(self):
        domains = {
            "complaint": ComplaintStatus,
            "voice": Submission.Status,
            "issue": CollectiveIssue.Status,
            "meeting": Meeting.Status,
        }
        for domain, choices in domains.items():
            for value in choices.values:
                with self.subTest(domain=domain, status=value):
                    self.assertIn(value, getattr(tones, domain.upper()))
                    self.assertIn(tones.tone(value, domain), tones.TONES)
                    self.assertEqual(tones.tone(value), tones.tone(value, domain))  # one meaning per value

    def test_the_owner_approved_mapping(self):
        pastel = {name: tones.TONE_PASTEL[tones.tone(value, domain)] for name, (value, domain) in {
            "complaint received": ("received", "complaint"), "complaint review": ("under_review", "complaint"),
            "complaint resolved": ("resolved", "complaint"), "complaint rejected": ("rejected", "complaint"),
            "voice waiting": ("waiting", "voice"), "voice reviewed": ("reviewed", "voice"), "voice answered": ("answered", "voice"),
            "issue open": ("support_open", "issue"), "issue closed": ("support_closed", "issue"),
            "meeting requested": ("requested", "meeting"), "meeting suggested": ("time_suggested", "meeting"),
            "meeting confirmed": ("confirmed", "meeting"), "meeting declined": ("declined", "meeting"),
            "meeting cancelled": ("cancelled", "meeting"), "meeting past": ("past", "meeting"),
            "account active": ("active", "account"), "account inactive": ("inactive", "account"),
            "represented": ("represented", "representation"), "awaiting": ("awaiting", "representation"),
        }.items()}
        self.assertEqual(pastel, {
            "complaint received": "sky", "complaint review": "amber", "complaint resolved": "mint", "complaint rejected": "rose",
            "voice waiting": "sky", "voice reviewed": "amber", "voice answered": "mint",
            "issue open": "mint", "issue closed": "sand",
            "meeting requested": "sky", "meeting suggested": "amber", "meeting confirmed": "mint",
            "meeting declined": "rose", "meeting cancelled": "rose", "meeting past": "sand",
            "account active": "mint", "account inactive": "sand",
            "represented": "mint", "awaiting": "amber",
        })

    def test_unknown_values_are_neutral(self):
        for value in ("", None, "nonsense", 42):
            with self.subTest(value=value):
                self.assertEqual(tones.tone(value), "neutral")
        self.assertEqual(tones.tone("received", "no-such-domain"), "neutral")
        self.assertEqual(tones.notification_tone("no.such_event"), "neutral")

    def test_voice_types_and_categories_have_fixed_pastels(self):
        for value in Submission.Type.values:
            self.assertIn(tones.voice_type_pastel(value), tones.PASTELS)
        self.assertEqual(len({tones.voice_type_pastel(v) for v in Submission.Type.values}), 3)
        self.assertEqual(tones.category_pastel(7), tones.category_pastel(7))
        self.assertIn(tones.category_pastel(3), tones.PASTELS)

    def test_every_notification_event_has_a_tone(self):
        from notifications.registry import REGISTRY
        for event in REGISTRY:
            with self.subTest(event=event):
                self.assertIn(event, tones.NOTIFICATION_TONES)
                self.assertNotEqual(tones.notification_icon(event), "bell")

    def test_template_filter_renders_the_tone(self):
        html = Template('{% load ui %}{{ "under_review"|tone }} {{ "past"|tone:"meeting" }} {{ "x"|tone }}').render(Context())
        self.assertEqual(html, "review neutral neutral")

    def test_the_css_defines_every_tone_and_pastel_class(self):
        css = (PROJECT / "static/css/app.css").read_text(encoding="utf-8")
        for name in (*tones.TONES, *tones.PASTELS, "accent"):
            with self.subTest(name=name):
                self.assertIn(f".sa-tone--{name}", css)


class TokenCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (PROJECT / "static/css/app.css").read_text(encoding="utf-8")

    def test_no_colour_values_below_the_token_layer(self):
        below = self.css[self.css.index("/* ---------- Base ---------- */"):]
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\((?!var\(--shadow-rgb\))", below)
        self.assertEqual(found, [])

    def test_dark_mode_overrides_the_same_tokens(self):
        dark = self.css[self.css.index('[data-theme="dark"] {'):]
        dark = dark[:dark.index("}")]
        for token in ("--bg:", "--surface:", "--text:", "--primary:", "--primary-soft:", "--mint-bg:", "--rose-ink:"):
            self.assertIn(token, dark)

    def test_inter_only(self):
        self.assertNotIn("Newsreader", self.css)
        self.assertNotIn("serif", self.css.replace("sans-serif", ""))

    def test_view_transitions_and_reduced_motion(self):
        self.assertIn("@view-transition { navigation: auto; }", self.css)
        self.assertIn("view-transition-name: sa-nav-pill", self.css)
        self.assertIn("view-transition-name: sa-sidebar", self.css)
        self.assertIn("view-transition-name: sa-topbar", self.css)
        reduced = self.css[self.css.rindex("@media (prefers-reduced-motion: reduce)"):]
        self.assertIn("animation: none !important", reduced)

    def test_no_templates_hard_code_colours(self):
        for path in (PROJECT / "templates").rglob("*.html"):
            if "admin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(template=str(path.relative_to(PROJECT))):
                self.assertIsNone(re.search(r"(?:fill|stroke|color|background)\s*[:=]\s*\"?#[0-9a-fA-F]{3,6}", text))


class CreateControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_academics()
        cls.home = cohort(cls.a)
        cls.student = make_student(academics=cls.a, full_name="Ali Khan")
        cls.classmate = make_student("70000001@student.uol.edu.pk", academics=cls.a, full_name="Sara Malik")
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.admin = make_super_admin()

    def test_exactly_one_action_is_a_button_and_two_or_more_a_menu(self):
        one = [{"label": "A"}]
        self.assertEqual(create_control(one), {"button": one[0], "menu": []})
        two = [{"label": "A"}, {"label": "B"}]
        self.assertEqual(create_control(two), {"button": None, "menu": two})
        self.assertEqual(create_control([]), {"button": None, "menu": []})

    def test_each_role(self):
        self.assertEqual([a["label"] for a in create_actions(self.advisor)], ["Schedule meeting"])
        self.assertEqual([a["label"] for a in create_actions(self.admin)], ["Add Batch Advisor"])
        self.assertEqual([a["label"] for a in create_actions(self.student)],
                         ["New complaint", "Voice submission", "Request meeting"])
        self.assertIsNotNone(create_control(create_actions(self.advisor))["button"])
        self.assertIsNotNone(create_control(create_actions(self.admin))["button"])
        self.assertIsNone(create_control(create_actions(self.student))["button"])
        for role, actions in CREATE_ACTIONS.items():
            for action in actions:
                self.assertIn(action.pastel, tones.PASTELS)

    def test_current_cr_and_gr_also_raise_a_section_issue(self):
        appoint_representatives(self.advisor, Cohort(*(part.pk for part in self.home)), cr=self.student, gr=self.classmate)
        for rep in (self.student, self.classmate):
            with self.subTest(rep=rep.get_full_name()):
                self.client.force_login(rep)
                html = self.client.get(reverse("student_home")).content.decode()
                menu = html[html.index('class="sa-pop sa-new"'):html.index("</details>", html.index('class="sa-pop sa-new"'))]
                self.assertEqual(re.findall(r"</span>([^<]+)</a>", menu),
                                 ["New complaint", "Voice submission", "Request meeting", "Raise a section issue"])
                self.assertIn(f'href="{reverse("student_issue_new")}"', menu)
        outsider = make_student("70000009@student.uol.edu.pk", academics=self.a, full_name="Omar Farooq")
        self.assertNotIn("Raise a section issue", [a["label"] for a in create_actions(outsider)])


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDERS)
class SignInMessageTests(TestCase):
    def assert_no_sign_in_message(self, response):
        html = response.content.decode()
        self.assertNotIn("Successfully signed in", html)
        self.assertNotIn("signed in as", html)
        self.assertNotIn("sa-toast", html)

    def test_no_message_after_sign_in_for_any_role(self):
        a = make_academics()
        make_student(STUDENT_EMAIL, academics=a)
        make_advisor(cohorts=[cohort(a)])
        make_super_admin()
        for email in (STUDENT_EMAIL, "advisor@uol.edu.pk", "head@uol.edu.pk"):
            with self.subTest(email=email):
                self.client.logout()
                response = google_sign_in(self.client, google_claims(email, sub=f"sub-{email}"))
                self.assertEqual(response.status_code, 302)
                landing = self.client.get(response["Location"], follow=True)
                self.assertEqual(landing.status_code, 200)
                self.assert_no_sign_in_message(landing)
                # Nor on the next page after it.
                self.assert_no_sign_in_message(self.client.get(reverse("home"), follow=True))

    def test_sign_out_is_a_toast_on_the_sign_in_page(self):
        self.client.force_login(make_super_admin())
        response = self.client.post(reverse("account_logout"), follow=True)
        self.assertRedirects(response, reverse("account_login"))
        html = response.content.decode()
        self.assertIn('class="sa-toasts"', html)
        self.assertIn("You’ve signed out", html)
        self.assertNotIn("sa-messages", html)


class MessageCopyTests(SimpleTestCase):
    """No "successfully" in any message the portal shows (docs/POLISH_V2.md copy rule)."""

    APPS = ("accounts", "academics", "complaints", "issues", "meetings", "notifications", "voice")

    def test_no_message_says_successfully(self):
        offenders = []
        for app in self.APPS:
            for path in (PROJECT / app).rglob("*.py"):
                if "tests" in path.parts or "migrations" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and "successful" in node.value.lower():
                        offenders.append(f"{path.relative_to(PROJECT)}:{node.lineno}")
        for path in (PROJECT / "templates").rglob("*"):
            if path.suffix in (".html", ".txt") and "successful" in path.read_text(encoding="utf-8").lower():
                offenders.append(str(path.relative_to(PROJECT)))
        self.assertEqual(offenders, [])

    def test_the_allauth_signed_in_message_is_silenced_at_the_adapter(self):
        from accounts.adapters import PortalAccountAdapter
        self.assertIn("account/messages/logged_in.txt", PortalAccountAdapter.SILENT_MESSAGES)


class GalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_super_admin()

    def test_404_when_debug_is_off(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("dev_component_gallery")).status_code, 404)

    @override_settings(DEBUG=True)
    def test_staff_only_even_in_debug(self):
        self.assertNotEqual(self.client.get(reverse("dev_component_gallery")).status_code, 200)  # to sign-in
        a = make_academics()
        for user in (make_student(academics=a), make_advisor(cohorts=[cohort(a)])):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("dev_component_gallery")).status_code, 404)

    @override_settings(DEBUG=True)
    def test_renders_every_component_in_light_and_dark(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dev_component_gallery"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for theme in ("light", "dark"):
            self.assertIn(f'data-theme="{theme}" aria-label="{theme.capitalize()} theme"', html)
        for piece in ("sa-stat ", "sa-citem", "sa-rows-head", "sa-stepper", "sa-timeline", "sa-dialog", "sa-toast",
                      "sa-empty--no-results", "sa-empty--all-caught-up", "sa-seg", "sa-dd", "sa-banner", "sa-hero-card",
                      "sa-role--cr", "Locked", "CR & GR only", "Private", "View only"):
            self.assertIn(piece, html)

    def test_not_linked_anywhere(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("super_admin_home")).content.decode()
        self.assertNotIn("/dev/ui/", html)


class FallbackTests(TestCase):
    """Dropdowns and segmented controls keep a real <select> / radio inputs, so forms work without JS."""

    def render(self, source, **context):
        request = RequestFactory().get("/list/", {"status": "received"})
        return Template("{% load ui %}" + source).render(Context({"request": request, **context}))

    def test_form_selects_stay_real_selects(self):
        from complaints.forms import ComplaintSubmissionForm
        html = str(ComplaintSubmissionForm()["category"])
        self.assertIn("<select", html)
        self.assertIn('class="form-select"', html)
        js = (PROJECT / "static/js/app.js").read_text(encoding="utf-8")
        self.assertIn('each("select.form-select, select[data-dropdown]", enhanceSelect)', js)
        self.assertIn('select.dispatchEvent(new Event("change", { bubbles: true }))', js)

    def test_segmented_radios_render_real_inputs(self):
        html = self.render('{% include "includes/ui/segmented.html" with name="view" choices=choices current="b" label="View" %}',
                           choices=[("a", "A"), ("b", "B")])
        self.assertEqual(html.count('type="radio" name="view"'), 2)
        self.assertIn('value="b" checked', html)
        self.assertIn('role="radiogroup"', html)

    def test_segmented_links_and_filter_dropdown_are_plain_links(self):
        choices = [("", "All"), ("received", "Received")]
        seg = self.render('{% include "includes/ui/segmented.html" with links=True param="status" choices=choices current="received" label="Status" %}',
                          choices=choices)
        self.assertIn('href="/list/?status=received" aria-current="true"', seg)
        dd = self.render('{% include "includes/ui/filter_chip.html" with label="Status" param="status" choices=choices current="received" %}',
                         choices=choices)
        self.assertIn("<details", dd)
        self.assertIn("<summary", dd)
        self.assertIn('href="/list/?status=received"', dd)

    def test_reset_pill_only_when_something_is_not_default(self):
        request = RequestFactory().get("/list/", {"status": "received", "sort": "newest", "page": "2"})
        render = lambda defaults: Template('{% include "includes/ui/reset_pill.html" %}').render(
            Context({"request": request, "list_keys": ["status", "sort", "page"], "list_defaults": defaults}))
        self.assertIn("Reset · 2", render({}))
        self.assertIn("Reset · 1", render({"sort": "newest"}))
        clean = RequestFactory().get("/list/")
        self.assertEqual(Template('{% include "includes/ui/reset_pill.html" %}').render(
            Context({"request": clean, "list_keys": ["status"]})).strip(), "")
