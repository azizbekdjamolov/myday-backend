from __future__ import annotations

from django.db import models

from . import encryption


class EncryptedTextField(models.TextField):
    """Encrypts content transparently at the ORM save boundary using AES-256-GCM.

    At rest the database only ever contains ciphertext envelopes. Reading the
    attribute returns the envelope (never the plaintext); decryption happens
    explicitly at the reveal/search boundaries so plaintext cannot leak through
    list/detail serializers, logging, or error responses.
    """

    description = "AES-256-GCM encrypted text"

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        if encryption.looks_encrypted(value):
            # Already encrypted (e.g. save() with an existing ciphertext).
            return value
        return encryption.encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        if not encryption.looks_encrypted(value):
            raise encryption.EncryptionError(
                "Stored value is not encrypted. Refusing to expose plaintext."
            )
        return value

    def to_python(self, value):
        # Keep the raw value (envelope) untouched; decryption is explicit.
        return value


class EncryptedCharField(EncryptedTextField):
    """CharField variant of :class:`EncryptedTextField`."""

    description = "AES-256-GCM encrypted string"
    max_length = None

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 512)
        super().__init__(*args, **kwargs)

    def get_internal_type(self):
        return "TextField"

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # The field is stored as TEXT in the DB; drop max_length noise.
        kwargs.pop("max_length", None)
        return name, path, args, kwargs