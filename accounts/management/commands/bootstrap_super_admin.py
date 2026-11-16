from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.services import BootstrapError, bootstrap_super_admin


class Command(BaseCommand):
    help = (
        "Create the initial Super Admin account (DEC-203). Refuses to run if a Super Admin "
        "already exists. No password is set: the Super Admin signs in with Google."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Official UOL staff email address.")
        parser.add_argument("--full-name", required=True, help="The Super Admin's full name.")

    def handle(self, *args, email, full_name, **options):
        try:
            user = bootstrap_super_admin(email=email, full_name=full_name)
        except BootstrapError as exc:
            raise CommandError(str(exc)) from exc
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Super Admin created for {user.email}. Sign in with this Google account to activate it."
            )
        )
