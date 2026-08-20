"""Safe development/demo data.

Creates demo users with clearly fake, development-only passwords. Never run
against a production database with real credentials.

Demo accounts (dev-only passwords):

    admin@example.com     / AdminPass123!    (admin, all modules)
    user@example.com      / UserPass123!     (normal user)
    bulldrop@example.com  / BullPass123!     (BullDrop access)
    intern@example.com    / InternPass123!   (Internlik access)
    both@example.com      / BothPass123!     (BullDrop + Internlik)
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.permissions.models import BULLDROP_ACCESS, INTERNLIK_ACCESS
from apps.permissions.services import grant_permission

User = get_user_model()

DEMO_USERS = [
    ("admin@example.com", "AdminPass123!", "Admin", {"admin": True}),
    ("user@example.com", "UserPass123!", "Normal User", {}),
    ("bulldrop@example.com", "BullPass123!", "BullDrop User", {BULLDROP_ACCESS}),
    ("intern@example.com", "InternPass123!", "Internlik User", {INTERNLIK_ACCESS}),
    ("both@example.com", "BothPass123!", "Both Modules", {BULLDROP_ACCESS, INTERNLIK_ACCESS}),
]


class Command(BaseCommand):
    help = "Create demo users (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete and recreate demo users.")

    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(email__in=[email for email, *_ in DEMO_USERS]).delete()
            self.stdout.write("Removed existing demo users.")

        for email, password, name, flags in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"name": name, "is_staff": True if "admin" in flags else False},
            )
            if created:
                user.set_password(password)
                user.is_superuser = "admin" in flags
                user.is_staff = "admin" in flags
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created {email}"))
            for code in flags:
                if code != "admin":
                    grant_permission(user=user, code=code)
            if "admin" in flags:
                from apps.permissions.services import ensure_admin_permission

                ensure_admin_permission(user)

        self.stdout.write(self.style.SUCCESS("Demo users ready."))