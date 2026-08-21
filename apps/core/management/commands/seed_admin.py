"""Create or update the deployment admin accounts.

Password is set directly (bypasses password validators) so short/numeric
passwords work; the account is created as a superuser with ADMIN_ACCESS.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.permissions.models import Permission
from apps.permissions.services import ensure_admin_permission

User = get_user_model()

ADMINS = [
    {
        "email": "admin@gmail.com",
        "password": "1234567890",
        "name": "Admin",
        "permissions": ["ADMIN_ACCESS"],
    },
    {
        "email": "adminaziz@gmail.com",
        "password": "1234567890",
        "name": "Aziz",
        "permissions": ["ADMIN_ACCESS", "BULLDROP_ACCESS"],
    },
]


class Command(BaseCommand):
    help = "Create or update the admin accounts."

    def handle(self, *args, **options):
        for cfg in ADMINS:
            user, created = User.objects.get_or_create(
                email=cfg["email"],
                defaults={"name": cfg["name"], "timezone": "Asia/Tashkent"},
            )
            user.name = cfg["name"]
            user.timezone = "Asia/Tashkent"
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(cfg["password"])
            user.save()
            ensure_admin_permission(user)
            for code in cfg["permissions"]:
                Permission.objects.get_or_create(user=user, code=code)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Created' if created else 'Updated'} admin {cfg['email']}"
                )
            )