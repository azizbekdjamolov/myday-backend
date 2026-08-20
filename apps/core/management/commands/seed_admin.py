"""Create or update the deployment admin account.

Password is set directly (bypasses password validators) so short/numeric
passwords work; the account is created as a superuser with ADMIN_ACCESS.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.permissions.services import ensure_admin_permission

User = get_user_model()

ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "1234567890"
ADMIN_NAME = "Admin"


class Command(BaseCommand):
    help = "Create or update the admin account (admin@gmail.com)."

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults={"name": ADMIN_NAME, "timezone": "Asia/Tashkent"},
        )
        user.name = ADMIN_NAME
        user.timezone = "Asia/Tashkent"
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(ADMIN_PASSWORD)
        user.save()
        ensure_admin_permission(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} admin {ADMIN_EMAIL}"
            )
        )