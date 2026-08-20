"""DRF permission classes for module-level access control.

These are the server-side gate for every protected module. Admin users
(superuser flag or ADMIN_ACCESS permission) implicitly hold every module
permission. Hiding navigation entries client-side is cosmetic only — these
classes are what actually protect the API.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from .models import ADMIN_ACCESS, BULLDROP_ACCESS, INTERNLIK_ACCESS


class HasBullDropAccess(BasePermission):
    message = "You do not have BullDrop access."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.is_superuser or user.has_bulldrop_access or user.has_admin_access)
        )


class HasInternlikAccess(BasePermission):
    message = "You do not have Internlik access."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.is_superuser or user.has_internlik_access or user.has_admin_access)
        )


class HasAdminAccess(BasePermission):
    message = "Administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.has_admin_access))


__all__ = ["HasBullDropAccess", "HasInternlikAccess", "HasAdminAccess"]