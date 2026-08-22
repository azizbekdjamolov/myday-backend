"""Storage and password helpers for private images.

Binary content is encrypted at rest in the same protected storage used by the
Vault, under a server-generated opaque key. The database row never contains
the plaintext password — only a one-way hash produced by Django's hardened
password hashers (PBKDF2-SHA256 with per-password salt by default).
"""

from __future__ import annotations

from apps.core.storage import get_storage


def store_image_bytes(*, data: bytes) -> tuple[str, str]:
    """Persist encrypted bytes; returns ``(storage_key, sha256_hex)``."""
    key, sha256 = get_storage().save(data)
    return key, sha256


def open_image_bytes(storage_key: str) -> bytes:
    return get_storage().open(storage_key)


def delete_image_file(storage_key: str) -> None:
    try:
        get_storage().delete(storage_key)
    except Exception:
        pass  # best effort; the DB row removal is authoritative
