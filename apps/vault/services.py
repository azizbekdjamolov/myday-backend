"""Vault unlock state and file helpers.

Unlock state lives server-side (Django cache) so the browser cannot forge it.
``VAULT_AUTOLOCK_MINUTES`` controls the TTL; the flag is refreshed on every
successful reveal.

Files are encrypted at rest in private storage; the database only keeps an
opaque key plus metadata.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache

from apps.core import encryption
from apps.core.storage import get_storage

_UNLOCK_PREFIX = "vault_unlock"


def decrypt_field(value: str) -> str:
    """Decrypt a stored envelope; empty values stay empty.

    Used ONLY at the explicit reveal boundary. Never call this for list,
    detail, or search serializers.
    """
    if not value:
        return ""
    try:
        return encryption.decrypt(value)
    except encryption.EncryptionError:
        return ""


def _cache_key(user) -> str:
    return f"{_UNLOCK_PREFIX}:{user.id}"


def unlock(user, *, ttl_minutes: int | None = None) -> float:
    """Mark the user's vault as unlocked and return the expiry timestamp."""
    ttl = ttl_minutes or settings.VAULT_AUTOLOCK_MINUTES
    expires = time.time() + ttl * 60
    cache.set(_cache_key(user), expires, timeout=ttl * 60 + 5)
    return expires


def is_unlocked(user) -> bool:
    expires = cache.get(_cache_key(user), 0)
    return expires > time.time()


def lock(user) -> None:
    cache.delete(_cache_key(user))


def unlock_expiry(user) -> float:
    return cache.get(_cache_key(user), 0)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def store_vault_file(*, user, data: bytes, filename: str, content_type: str) -> tuple[str, str, int]:
    """Persist an encrypted blob; returns (storage_key, sha256, size)."""
    key, sha256 = get_storage().save(data, name_hint=filename)
    return key, sha256, len(data)


def open_vault_file(file_obj) -> bytes:
    return get_storage().open(file_obj.storage_key)


def delete_vault_file(file_obj) -> None:
    try:
        get_storage().delete(file_obj.storage_key)
    except Exception:
        pass  # best effort; the row delete below is what matters


def delete_item_files(user, item) -> None:
    """Remove all files attached to a vault item, then their rows."""
    for f in item.files.all():
        try:
            get_storage().delete(f.storage_key)
        except Exception:
            pass
    item.files.all().delete()