"""Request correlation and access logging middleware."""

from __future__ import annotations

import logging
import threading
import time
import uuid

from django.conf import settings

_logger = None
_local = threading.local()


def get_request_id() -> str:
    return getattr(_local, "request_id", "-")


class RequestIdMiddleware:
    """Assign a correlation id to every request for log tracing.

    Honors a client-supplied ``X-Request-ID`` when present (bounded length),
    otherwise generates one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", "")
        if len(request_id) > 64 or not request_id.isalnum():
            request_id = uuid.uuid4().hex[:16]
        _local.request_id = request_id
        request.request_id = request_id

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        global _logger
        if _logger is None:
            _logger = logging.getLogger("django.request")

        if settings.DEBUG or request.path.startswith("/api/"):
            _logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                extra={"request_id": request_id},
            )
        return response