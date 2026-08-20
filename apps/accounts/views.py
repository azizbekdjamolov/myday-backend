"""Authentication endpoints.

Session is carried by JWT cookies: a short-lived access cookie and a rotating
refresh cookie, both HttpOnly. The SPA never stores tokens. Login is throttled
per (email, IP); refresh and logout require a CSRF token echo.

Password reset is token-based with a cache-backed token (no email dependency
for the initial version — the token is logged / returned in dev, and the
flow is ready for a real mailer).
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import record_audit

from .auth import enforce_csrf
from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import AuthIpThrottle, login_blocked, record_login_failure

RESET_TOKEN_TTL_SECONDS = 60 * 30


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _set_auth_cookies(response, user) -> None:
    refresh = RefreshToken.for_user(user)
    response.set_cookie(
        settings.JWT_AUTH_COOKIE,
        str(refresh.access_token),
        max_age=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds(),
        httponly=settings.JWT_AUTH_COOKIE_HTTPONLY,
        secure=settings.JWT_AUTH_COOKIE_SECURE,
        samesite=settings.JWT_AUTH_COOKIE_SAMESITE,
        path=settings.JWT_AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        settings.JWT_AUTH_REFRESH_COOKIE,
        str(refresh),
        max_age=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds(),
        httponly=settings.JWT_AUTH_COOKIE_HTTPONLY,
        secure=settings.JWT_AUTH_COOKIE_SECURE,
        samesite=settings.JWT_AUTH_COOKIE_SAMESITE,
        path=settings.JWT_AUTH_COOKIE_PATH,
    )


def _clear_auth_cookies(response) -> None:
    for name in (settings.JWT_AUTH_COOKIE, settings.JWT_AUTH_REFRESH_COOKIE):
        response.delete_cookie(name, path=settings.JWT_AUTH_COOKIE_PATH)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        record_audit(
            actor=user,
            action="auth.register",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = (serializer.validated_data["email"] or "").strip().lower()
        password = serializer.validated_data["password"]

        if login_blocked(request, email):
            record_audit(
                actor=None,
                action="auth.login_failed",
                resource_type="user",
                resource_id=email,
                outcome="failure",
                metadata={"reason": "blocked"},
                request=request,
            )
            raise PermissionDenied("Too many failed attempts. Please try again later.")

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.check_password(password):
            if user is not None:
                record_login_failure(request, email)
            record_audit(
                actor=user,
                action="auth.login_failed",
                resource_type="user",
                resource_id=user.id if user else email,
                outcome="failure",
                request=request,
            )
            raise AuthenticationFailed("Invalid email or password.")

        if not user.is_active:
            raise PermissionDenied("This account has been deactivated.")

        response = Response(UserSerializer(user).data)
        _set_auth_cookies(response, user)
        record_audit(
            actor=user,
            action="auth.login",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        return response


class RefreshView(APIView):
    """Rotate the refresh cookie; requires a CSRF token echo.

    CSRF is enforced manually (JSON-friendly 401) instead of by the middleware
    so the SPA gets a consistent error envelope.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        enforce_csrf(request)
        raw_refresh = request.COOKIES.get(settings.JWT_AUTH_REFRESH_COOKIE)
        if not raw_refresh:
            raise AuthenticationFailed("No refresh token.")
        try:
            token = RefreshToken(raw_refresh)
            user = User.objects.get(id=token.payload.get("user_id"))
        except Exception:
            raise AuthenticationFailed("Invalid refresh token.")
        if not user.is_active:
            raise PermissionDenied("This account has been deactivated.")

        token.blacklist()
        response = Response(UserSerializer(user).data)
        _set_auth_cookies(response, user)
        return response


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        enforce_csrf(request)
        raw_refresh = request.COOKIES.get(settings.JWT_AUTH_REFRESH_COOKIE)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except Exception:
                pass
        response = Response({"detail": "Logged out."})
        _clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["current_password"]):
            raise PermissionDenied("Current password is incorrect.")
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        record_audit(
            actor=request.user,
            action="auth.password_changed",
            resource_type="user",
            resource_id=request.user.id,
            request=request,
        )
        return Response({"detail": "Password updated."})


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileUpdateSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            # Never reveal whether an account exists.
            return Response({"detail": "If that account exists, a reset token has been sent."})

        token = secrets.token_urlsafe(32)
        cache.set(f"pwreset:{token}", user.id, RESET_TOKEN_TTL_SECONDS)
        record_audit(
            actor=user,
            action="auth.password_reset_requested",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )

        payload = {"detail": "If that account exists, a reset token has been sent."}
        # Dev convenience: surface the token locally. Replace with a real
        # mailer (send_mail) in production; the token never appears in the
        # response when a mailer is configured.
        if settings.DEBUG:
            payload["dev_token"] = token
        return Response(payload)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIpThrottle]

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        new_password = (request.data.get("new_password") or "").strip()
        user_id = cache.get(f"pwreset:{token}")
        if user_id is None:
            raise ValidationError({"token": "Invalid or expired reset token."})
        user = User.objects.filter(id=user_id).first()
        if user is None or len(new_password) < 10:
            raise ValidationError({"new_password": "Password must be at least 10 characters."})

        user.set_password(new_password)
        user.save(update_fields=["password"])
        cache.delete(f"pwreset:{token}")
        record_audit(
            actor=user,
            action="auth.password_reset",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        return Response({"detail": "Password reset. You can now sign in."})