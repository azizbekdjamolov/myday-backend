"""Structured logging with sensitive-data redaction.

Production logs are JSON lines::

    {"asctime": "...", "levelname": "INFO", "name": "apps.bulldrop.views",
     "request_id": "abc123", "message": "bulldrop claim accepted"}

Never log: passwords, decrypted vault values, encryption keys, tokens, or
personal data. The :class:`RedactionFilter` scrubs any message containing a
sensitive field name (configurable via ``SENSITIVE_LOG_FIELDS``), replacing
the value with ``[REDACTED]``.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class RequestIdFilter(logging.Filter):
    """Attach the request correlation id (set by RequestIdMiddleware)."""

    def filter(self, record):
        record.request_id = getattr(record, "request_id", None) or "-"
        return True


class RedactionFilter(logging.Filter):
    """Redact known sensitive values inside log records."""

    def filter(self, record):
        fields = getattr(settings, "SENSITIVE_LOG_FIELDS", [])
        msg = record.getMessage()
        redacted = msg
        for field in fields:
            pattern = re.compile(rf'("?{re.escape(field)}"?\s*[:=]\s*)"[^"]*"|({re.escape(field)}\s*=\s*)\S+', re.IGNORECASE)
            redacted = pattern.sub(rf"\1[REDACTED]", redacted)
        # Generic email scrub: user identity data should never reach logs.
        redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)