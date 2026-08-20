from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone as dj_timezone
from timezone_field import TimeZoneField

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=150, blank=True, default="")
    timezone = TimeZoneField(default="Asia/Tashkent", help_text="Used for all schedule and reminder calculations.")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=dj_timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]

    @property
    def has_bulldrop_access(self) -> bool:
        return self.permissions.filter(code="BULLDROP_ACCESS").exists()

    @property
    def has_internlik_access(self) -> bool:
        return self.permissions.filter(code="INTERNLIK_ACCESS").exists()

    @property
    def has_admin_access(self) -> bool:
        return self.permissions.filter(code="ADMIN_ACCESS").exists()

    def permission_codes(self) -> set[str]:
        return set(self.permissions.values_list("code", flat=True))