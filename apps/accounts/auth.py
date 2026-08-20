"""JWT authentication via HttpOnly cookies with CSRF protection.

The SPA never stores tokens in localStorage. The access token lives in an
HttpOnly cookie (short-lived, rotated via a refresh cookie). Because cookie
authentication is vulnerable to CSRF, unsafe methods require a valid
``X-CSRFToken`` header matching the ``myday_csrftoken`` cookie. That check is
enforced by Django's ``CsrfViewMiddleware`` for every non-exempt endpoint and
additionally (with a JSON-friendly 401) by the refresh/logout views.

Clients that authenticate with a ``Bearer`` token in the ``Authorization``
header (server-to-server) bypass the cookie path entirely and are not subject
to the CSRF check.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            return (user, validated_token)

        cookie_name = settings.JWT_AUTH_COOKIE
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        return (user, validated_token)


def enforce_csrf(request) -> None:
    """Require a valid X-CSRFToken header matching the CSRF cookie.

    Used by cookie-authenticated unsafe endpoints (refresh, logout) where the
    access token itself is not proof of intent.

    The comparison mirrors Django's own ``CsrfViewMiddleware`` logic so it
    stays correct across Django versions.
    """
    from django.middleware.csrf import (
        CSRF_TOKEN_LENGTH,
        InvalidTokenFormat,
        _check_token_format,
        _does_token_match,
        _unmask_cipher_token,
        get_token,
    )

    cookie_token = request.META.get("CSRF_COOKIE")
    if cookie_token is None:
        cookie_token = get_token(request)

    # The cookie may be a masked token; reduce it to the raw secret.
    csrf_secret = _unmask_cipher_token(cookie_token) if len(cookie_token) == CSRF_TOKEN_LENGTH else cookie_token

    header_token = request.META.get("HTTP_X_CSRFTOKEN")
    if not header_token:
        raise AuthenticationFailed("CSRF token missing.")
    try:
        _check_token_format(header_token)
        if not _does_token_match(header_token, csrf_secret):
            raise AuthenticationFailed("CSRF token invalid.")
    except (InvalidTokenFormat, TypeError, ValueError):
        raise AuthenticationFailed("CSRF token invalid.")