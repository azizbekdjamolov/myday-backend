"""Private, password-protected image storage.

This module is intentionally independent of the Vault: images are their own
first-class private objects. Every image belongs to exactly one owner and is
protected by its own password (stored only as a modern one-way hash — never
plaintext, never reversible).

The binary content lives in encrypted-at-rest private storage behind an opaque
random ``storage_key``; there is no public URL of any kind. Bytes are served
exclusively through an ownership + password verified API action.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

NAME_MAX_LENGTH = 200


class Image(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="images",
    )
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    # Server-generated opaque key into the private secure storage.
    storage_key = models.CharField(max_length=128, unique=True)
    # Verified server-side from magic bytes, not client-supplied MIME.
    content_type = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    # One-way hash (PBKDF2/Argon2 via Django hashers). Never the plaintext.
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.owner_id})"

    def check_image_password(self, raw_password: str) -> bool:
        from django.contrib.auth.hashers import check_password

        return check_password(raw_password, self.password_hash)

    def set_image_password(self, raw_password: str) -> None:
        from django.contrib.auth.hashers import make_password

        self.password_hash = make_password(raw_password)
