from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.models import User

from .helpers import STUDENT_EMAIL, make_advisor


def bootstrap(email="Head.Advisor@UOL.edu.pk", full_name="Head Advisor"):
    out = StringIO()
    call_command("bootstrap_super_admin", email=email, full_name=full_name, stdout=out)
    return out.getvalue()


class BootstrapSuperAdminTests(TestCase):
    def test_creates_the_first_super_admin_without_password(self):
        output = bootstrap()

        head = User.objects.get()
        self.assertEqual(head.email, "head.advisor@uol.edu.pk")
        self.assertEqual(head.full_name, "Head Advisor")
        self.assertEqual(head.role, User.Role.SUPER_ADMIN)
        self.assertEqual((head.is_staff, head.is_superuser, head.is_active), (True, True, True))
        self.assertFalse(head.has_usable_password())
        self.assertIn("Sign in with this Google account", output)

    def test_refuses_once_a_super_admin_exists(self):
        bootstrap()
        with self.assertRaisesMessage(CommandError, "already exists"):
            bootstrap(email="second@uol.edu.pk")
        self.assertEqual(User.objects.count(), 1)

    def test_refuses_non_staff_emails(self):
        for email in (STUDENT_EMAIL, "head@gmail.com", "not-an-email"):
            with self.subTest(email=email), self.assertRaises(CommandError):
                bootstrap(email=email)
        self.assertFalse(User.objects.exists())

    def test_refuses_an_email_that_already_has_an_account(self):
        make_advisor("head.advisor@uol.edu.pk")
        with self.assertRaisesMessage(CommandError, "already exists"):
            bootstrap()
        self.assertFalse(User.objects.filter(role=User.Role.SUPER_ADMIN).exists())

    def test_requires_both_arguments(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_super_admin", email="head@uol.edu.pk")
