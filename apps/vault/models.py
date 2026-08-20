"""Personal vault models.

Sensitive fields (username, password, notes) are encrypted at rest with
AES-256-GCM via :class:`apps.core.fields.EncryptedCharField`. Decrypted values
are never included in list/retrieve serializers — only a re-authenticated
reveal action returns them.

Files are stored in the private secure storage (encrypted blobs) with an
opaque key; they are served only through the ownership-checked download
endpoint.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedCharField, EncryptedTextField

CATEGORY_CHOICES = [
    ("accounts", "Accounts"),
    ("passwords", "Passwords"),
    ("images", "Images"),
    ("documents", "Documents"),
    ("notes", "Notes"),
    ("custom", "Custom"),
]


class VaultItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vault_items")
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="notes")
    title = models.CharField(max_length=200)
    encrypted_username = EncryptedCharField(blank=True, default="")
    encrypted_password = EncryptedCharField(blank=True, default="")
    encrypted_notes = EncryptedTextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "category"])]

    def __str__(self):
        return f"{self.title} ({self.user_id})"

    @property
    def has_username(self) -> bool:
        return bool(self.encrypted_username)

    @property
    def has_password(self) -> bool:
        return bool(self.encrypted_password)

    @property
    def has_notes(self) -> bool:
        return bool(self.encrypted_notes)


class VaultFile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vault_files")
    vault_item = models.ForeignKey(
        VaultItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    storage_key = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename