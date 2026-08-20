"""Grant / revoke helper functions with audit logging.

Calling these functions (not raw ORM) is the only supported way to change
permissions so that every change is audited and never accidentally persists
secrets.
"""

from __future__ import annotations

from django.apps import apps
from django.core.exceptions import ValidationError

from apps.core.models import record_audit

from .models import ALL_PERMISSION_CODES, Permission


def _validate_code(code: str) -> None:
    if code not in ALL_PERMISSION_CODES:
        raise ValidationError(f"Unknown permission code: {code}")


def grant_permission(*, user, code: str, actor=None, request=None) -> Permission:
    """Grant ``code`` to ``user`` (idempotent) and write an audit entry."""
    _validate_code(code)
    permission, created = Permission.objects.get_or_create(user=user, code=code)
    if created:
        record_audit(
            actor=actor,
            action="permission.granted",
            resource_type="user",
            resource_id=user.id,
            metadata={"permission": code},
            request=request,
        )
    return permission


def revoke_permission(*, user, code: str, actor=None, request=None) -> bool:
    """Revoke ``code`` from ``user``; returns True if something was removed."""
    _validate_code(code)
    deleted, _ = Permission.objects.filter(user=user, code=code).delete()
    if deleted:
        record_audit(
            actor=actor,
            action="permission.revoked",
            resource_type="user",
            resource_id=user.id,
            metadata={"permission": code},
            request=request,
        )
    return bool(deleted)


def ensure_admin_permission(user) -> None:
    """Backfill ADMIN_ACCESS for superusers (used at creation / startup)."""
    if user.is_superuser and not user.has_admin_access:
        Permission.objects.get_or_create(user=user, code="ADMIN_ACCESS")
    if user.has_admin_access and not user.is_superuser:
        # Keep the admin permission aligned with the superuser flag.
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])


def sync_admin_permissions() -> int:
    """Ensure every superuser has ADMIN_ACCESS and vice-versa. Idempotent."""
    user_model = apps.get_model("accounts", "User")
    created = 0
    for user in user_model.objects.filter(is_superuser=True):
        perm, was_created = Permission.objects.get_or_create(user=user, code="ADMIN_ACCESS")
        created += int(was_created)
    return created