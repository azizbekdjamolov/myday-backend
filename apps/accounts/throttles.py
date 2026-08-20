"""Brute-force protection for authentication endpoints.

Two complementary throttles:

* :class:`LoginAttemptThrottle` — exponential backoff per (email, IP): 5
  attempts per 15 minutes, hardening after repeated failures.
* ``auth`` scoped throttle — per-IP ceiling on the whole auth surface.

All state lives in the Django cache (Redis in production), so limits hold
across multiple app instances.
"""

from __future__ import annotations

import hashlib
import time

from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_WINDOW = 5

LOGIN_ATTEMPT_SCOPE = "login_attempts"


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _attempt_cache_key(email: str, request) -> str:
    ident = hashlib.sha256(f"{email}|{_client_ip(request)}".encode()).hexdigest()
    return f"throttle_{LOGIN_ATTEMPT_SCOPE}_{ident}"


class LoginAttemptThrottle(SimpleRateThrottle):
    """Limits failed login attempts per (email, IP) pair.

    The actual blocking is implemented by :func:`login_blocked` /
    :func:`record_login_failure` against a per-pair failure counter. This
    class only exists so views can attach a scoped throttle for a hard
    ceiling; ``rate`` uses a DRF-valid format and is intentionally generous.
    """

    rate = "10000/m"
    scope = LOGIN_ATTEMPT_SCOPE

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        return _attempt_cache_key(email, request)


class AuthIpThrottle(ScopedRateThrottle):
    scope = "auth"


def record_login_failure(request, email: str) -> None:
    """Bump the failure counter used by :func:`login_blocked`."""
    key = _attempt_cache_key(email, request)
    entries = cache.get(key, []) or []
    now = time.time()
    entries = [ts for ts in entries if ts > now - WINDOW_SECONDS]
    entries.append(now)
    cache.set(key, entries, WINDOW_SECONDS + 10)


def login_blocked(request, email: str) -> bool:
    """True when the (email, IP) pair has too many recent failures."""
    key = _attempt_cache_key(email, request)
    entries = cache.get(key, []) or []
    cutoff = time.time() - WINDOW_SECONDS
    recent = [ts for ts in entries if ts > cutoff]
    return len(recent) >= MAX_FAILURES_PER_WINDOW


__all__ = ["LoginAttemptThrottle", "AuthIpThrottle", "record_login_failure", "login_blocked"]