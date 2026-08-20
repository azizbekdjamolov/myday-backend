"""Consistent API error handling.

Every API error is returned in a uniform envelope::

    HTTP 400/403/404/...

    {
      "error": {
        "code": "validation_error",
        "message": "Human readable message.",
        "details": { ... }   // optional, field-level errors
      }
    }

The handler never leaks stack traces, database internals, or paths in
production responses.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Domain error with an explicit HTTP status and machine-readable code."""

    status_code = 400
    code = "api_error"

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None, details=None):
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(APIError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(APIError):
    status_code = 403
    code = "permission_denied"


class ConflictError(APIError):
    status_code = 409
    code = "conflict"


class ValidationError(APIError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(APIError):
    status_code = 429
    code = "rate_limited"


def _code_for_drf(exc: drf_exceptions.APIException) -> str:
    mapping = {
        drf_exceptions.AuthenticationFailed: "authentication_failed",
        drf_exceptions.NotAuthenticated: "not_authenticated",
        drf_exceptions.PermissionDenied: "permission_denied",
        drf_exceptions.NotFound: "not_found",
        drf_exceptions.ValidationError: "validation_error",
        drf_exceptions.MethodNotAllowed: "method_not_allowed",
        drf_exceptions.NotAcceptable: "not_acceptable",
        drf_exceptions.UnsupportedMediaType: "unsupported_media_type",
        drf_exceptions.Throttled: "rate_limited",
        drf_exceptions.ParseError: "malformed_request",
    }
    return mapping.get(type(exc), "request_error")


def _format_detail(detail):
    if isinstance(detail, dict):
        return {str(k): _format_detail(v) for k, v in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_format_detail(item) for item in detail]
    return str(detail)


def api_exception_handler(exc, context):
    # Domain errors raised directly by views/services (ConflictError, etc.).
    if isinstance(exc, APIError):
        return Response(
            {"error": {"code": exc.code, "message": exc.message, **({"details": exc.details} if exc.details else {})}},
            status=exc.status_code,
        )

    response = exception_handler(exc, context)

    # Django validation errors (e.g. raised in clean()) must surface uniformly.
    if response is None and isinstance(exc, DjangoValidationError):
        exc = drf_exceptions.ValidationError(exc.messages)
        response = exception_handler(exc, context)

    if response is None and isinstance(exc, IntegrityError):
        # Convert unique-constraint races into a clean conflict.
        exc = drf_exceptions.ValidationError({"detail": "A conflicting record already exists."})
        response = exception_handler(exc, context)

    if response is None:
        # Unhandled exception. Log it (with request context) but respond with a
        # generic message in production so internals are never leaked.
        logger.exception("Unhandled exception in request", exc_info=exc)
        response = Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
            status=500,
        )
        return response

    detail = response.data
    message = str(_format_detail(detail.get("detail", "Request could not be processed.")))
    code = _code_for_drf(exc)

    body = {"error": {"code": code, "message": message}}

    # Attach field-level details for 422-style validation errors only, where
    # the payload shape is well understood.
    if isinstance(detail, dict) and "detail" not in detail:
        body["error"]["details"] = _format_detail(detail)
    elif code == "validation_error" and isinstance(detail, dict) and isinstance(detail.get("detail"), dict):
        body["error"]["details"] = _format_detail(detail["detail"])

    if code == "rate_limited":
        wait = getattr(exc, "wait", None)
        if wait is not None:
            body["error"]["retry_after"] = int(wait)

    response.data = body
    return response