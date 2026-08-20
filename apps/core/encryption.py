"""Authenticated encryption for the Vault.

Uses AES-256-GCM with random 96-bit nonces. Each value is encrypted with an
independent random data key that is itself wrapped by the master key. This
"envelope" design keeps the implementation simple while allowing key rotation
(the data keys are re-wrapped) without re-encrypting stored values.

Master key is loaded from settings (environment), never hardcoded. In
development the master key defaults to a deterministic value derived from the
Django secret so the app runs out of the box; production must provide a real
random key via ``VAULT_MASTER_KEY``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_ENVELOPE_VERSION = 1
_ENVELOPE_SEPARATOR = "$"

# Names of fields we must never log.
_FORBIDDEN_SUBSTRINGS = ("secret", "password", "token", "key", "authorization")


def _build_envelope(payload_b64: str) -> str:
    """Envelope shape: ``$<version>$<base64 payload>`` (starts with '$' so
    :func:`looks_encrypted` is a cheap, unambiguous prefix check)."""
    return f"{_ENVELOPE_SEPARATOR}{_ENVELOPE_VERSION}{_ENVELOPE_SEPARATOR}{payload_b64}"


def _parse_envelope(envelope: str) -> tuple[int, str]:
    if not isinstance(envelope, str) or not envelope.startswith(_ENVELOPE_SEPARATOR):
        raise EncryptionError("Malformed encrypted value")
    body = envelope[1:]
    version, payload_b64 = body.split(_ENVELOPE_SEPARATOR, 1)
    return int(version), payload_b64


class EncryptionError(Exception):
    """Raised when a value cannot be encrypted or decrypted."""


class IntegrityError(EncryptionError):
    """Raised when decrypted content fails authentication (tamper detected)."""


def _master_key() -> bytes:
    key = getattr(settings, "VAULT_MASTER_KEY", None)
    if key:
        return key
    # Development fallback: derive a stable 32-byte key from DJANGO_SECRET_KEY.
    # This is NOT secure enough for production; REQUIRE_VAULT_MASTER_KEY=1
    # turns it into a hard error.
    if settings.REQUIRE_VAULT_MASTER_KEY:
        raise ImproperlyConfigured("VAULT_MASTER_KEY must be set when REQUIRE_VAULT_MASTER_KEY=1")
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()[:32]


def _random_data_key() -> bytes:
    return os.urandom(32)


def encrypt(value: str) -> str:
    """Encrypt a UTF-8 string; returns a versioned, base64 envelope string."""
    if value is None:
        raise EncryptionError("Cannot encrypt None")
    data_key = _random_data_key()
    nonce = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, value.encode("utf-8"), None)
    wrapped_key = AESGCM(_master_key()).encrypt(nonce, data_key, None)
    envelope = {
        "v": _ENVELOPE_VERSION,
        "n": base64.b64encode(nonce).decode(),
        "k": base64.b64encode(wrapped_key).decode(),
        "c": base64.b64encode(ciphertext).decode(),
    }
    return _build_envelope(base64.b64encode(json.dumps(envelope).encode()).decode())


def decrypt(envelope: str) -> str:
    """Decrypt an envelope produced by :func:`encrypt`. Raises on tampering."""
    try:
        version, payload_b64 = _parse_envelope(envelope)
        if int(version) != _ENVELOPE_VERSION:
            raise EncryptionError(f"Unsupported envelope version: {version}")
        envelope = json.loads(base64.b64decode(payload_b64))
        nonce = base64.b64decode(envelope["n"])
        wrapped_key = base64.b64decode(envelope["k"])
        ciphertext = base64.b64decode(envelope["c"])
    except (ValueError, KeyError, json.JSONDecodeError, TypeError, binascii.Error, EncryptionError) as exc:
        raise EncryptionError("Malformed encrypted value") from exc

    try:
        data_key = AESGCM(_master_key()).decrypt(nonce, wrapped_key, None)
        plaintext = AESGCM(data_key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise IntegrityError("Encrypted value failed authentication check (tampered or wrong key)") from exc
    return plaintext.decode("utf-8")


def encrypt_bytes(plaintext: bytes) -> str:
    """Encrypt arbitrary bytes (e.g. uploaded files) into a base64 envelope."""
    data_key = _random_data_key()
    nonce = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, None)
    wrapped_key = AESGCM(_master_key()).encrypt(nonce, data_key, None)
    envelope = {
        "v": _ENVELOPE_VERSION,
        "n": base64.b64encode(nonce).decode(),
        "k": base64.b64encode(wrapped_key).decode(),
        "c": base64.b64encode(ciphertext).decode(),
    }
    return _build_envelope(base64.b64encode(json.dumps(envelope).encode()).decode())


def decrypt_bytes(envelope: str) -> bytes:
    """Decrypt an envelope produced by :func:`encrypt_bytes`."""
    try:
        version, payload_b64 = _parse_envelope(envelope)
        if int(version) != _ENVELOPE_VERSION:
            raise EncryptionError(f"Unsupported envelope version: {version}")
        env = json.loads(base64.b64decode(payload_b64))
        nonce = base64.b64decode(env["n"])
        wrapped_key = base64.b64decode(env["k"])
        ciphertext = base64.b64decode(env["c"])
    except (ValueError, KeyError, json.JSONDecodeError, TypeError, binascii.Error, EncryptionError) as exc:
        raise EncryptionError("Malformed encrypted value") from exc

    try:
        data_key = AESGCM(_master_key()).decrypt(nonce, wrapped_key, None)
        plaintext = AESGCM(data_key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise IntegrityError("Encrypted value failed authentication check (tampered or wrong key)") from exc
    return plaintext


def looks_encrypted(value: str) -> bool:
    """True for values produced by :func:`encrypt` (prefix check only)."""
    return isinstance(value, str) and value.startswith(_ENVELOPE_SEPARATOR)


__all__ = [
    "EncryptionError",
    "IntegrityError",
    "encrypt",
    "decrypt",
    "encrypt_bytes",
    "decrypt_bytes",
    "looks_encrypted",
]