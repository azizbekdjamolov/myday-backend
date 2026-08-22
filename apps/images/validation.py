"""Upload validation based on file content, not client claims.

The extension and the ``Content-Type`` header of an upload are attacker
controlled, so the real format is derived from magic bytes. Anything that is
not a supported raster image is rejected before it is ever written to storage.

Supported: JPEG, PNG, WEBP.
"""

from __future__ import annotations

SUPPORTED_IMAGE_TYPES: dict[str, str] = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MAX_NAME_LENGTH = 200


class InvalidImageError(Exception):
    """Raised when an upload fails server-side content validation."""


def _sniff_format(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    # WEBP: bytes 0-3 'RIFF', 8-11 'WEBP'
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def sniff_image_format(data: bytes) -> str | None:
    """Return the detected format name ('jpeg'|'png'|'webp') or None."""
    if not data:
        return None
    # A real image of any of these formats needs at least a dozen bytes; tiny
    # payloads are polyglot/probe attempts.
    if len(data) < 32:
        return None
    return _sniff_format(data[:16])


def validate_upload(*, data: bytes, declared_name: str) -> tuple[str, str]:
    """Validate an uploaded image.

    Returns ``(content_type, safe_name)``. Raises :class:`InvalidImageError`
    when the payload is not a genuine supported image or the display name is
    unusable.
    """
    fmt = sniff_image_format(data)
    if fmt is None:
        raise InvalidImageError("Unsupported image type. Use JPG, JPEG, PNG or WEBP.")

    # The original filename is only ever used for a sanitised display hint —
    # never as part of the storage path.
    base = (declared_name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    ext = ""
    if "." in base:
        candidate = base.rsplit(".", 1)[-1].lower()
        ext = f".{candidate}" if f".{candidate}" in ALLOWED_EXTENSIONS else ""

    return SUPPORTED_IMAGE_TYPES[fmt], ext
