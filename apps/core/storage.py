"""Protected file storage abstraction.

The Vault stores files in a private root that is never served by the web
server. The :class:`SecureStorage` protocol abstracts the physical location so
object storage (S3, GCS, ...) can be added later without touching callers.

All stored blobs are encrypted at rest with AES-256-GCM; the returned handle
is an opaque ID used to retrieve the file through the ownership-checked API
endpoint.
"""

from __future__ import annotations

import hashlib
import os
import uuid

from django.conf import settings

from .encryption import decrypt_bytes, encrypt_bytes

CHUNK_SIZE = 1024 * 1024


class StorageError(Exception):
    pass


class NotFound(StorageError):
    pass


class LocalSecureStorage:
    """Encrypted-at-rest storage on the local filesystem."""

    def __init__(self, root: str | None = None):
        self.root = root or settings.PRIVATE_MEDIA_ROOT

    def _path(self, key: str) -> str:
        # Key is generated server-side; guard against traversal regardless.
        safe = os.path.basename(key)
        return os.path.join(self.root, safe[:2], safe)

    def save(self, data: bytes, *, name_hint: str = "") -> tuple[str, str]:
        """Encrypt ``data`` and persist it. Returns ``(key, sha256_hex)``."""
        os.makedirs(os.path.join(self.root), exist_ok=True)
        key = uuid.uuid4().hex
        os.makedirs(os.path.join(self.root, key[:2]), exist_ok=True)
        path = self._path(key)
        blob = encrypt_bytes(data).encode("ascii")
        tmp_path = path + ".tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(blob)
        os.replace(tmp_path, path)
        return key, hashlib.sha256(data).hexdigest()

    def open(self, key: str) -> bytes:
        path = self._path(key)
        if not os.path.exists(path):
            raise NotFound(f"Blob not found: {key}")
        with open(path, "rb") as fh:
            envelope = fh.read().decode("ascii")
        return decrypt_bytes(envelope)

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# Default storage instance. Swap to an object-storage implementation by
# changing settings.SECURE_STORAGE_BACKEND.
secure_storage = LocalSecureStorage()


def get_storage():
    backend = getattr(settings, "SECURE_STORAGE_BACKEND", "local")
    if backend == "local":
        return secure_storage
    raise StorageError(f"Unknown secure storage backend: {backend}")


__all__ = ["StorageError", "NotFound", "secure_storage", "get_storage"]