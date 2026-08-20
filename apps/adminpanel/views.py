from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.models import record_audit
from apps.permissions.permissions import HasAdminAccess
from apps.permissions.services import grant_permission, revoke_permission

from .serializers import AdminUserSerializer, PermissionChangeSerializer

User = get_user_model()


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin-only user management: list, permissions, activate/deactivate."""

    permission_classes = [HasAdminAccess]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        queryset = User.objects.prefetch_related("permissions").order_by("email")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(email__icontains=search)
        return queryset

    @action(detail=True, methods=["post"])
    def permission(self, request, pk=None):
        user = self.get_object()
        serializer = PermissionChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        permission_code = serializer.validated_data["permission"]
        action = serializer.validated_data["action"]

        if user.id == request.user.id:
            raise ValidationError({"permission": "You cannot change your own permissions."})

        if action == "grant":
            grant_permission(user=user, code=permission_code, actor=request.user, request=request)
        else:
            revoke_permission(user=user, code=permission_code, actor=request.user, request=request)

        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        if user.id == request.user.id:
            raise ValidationError({"detail": "You cannot deactivate your own account."})
        user.is_active = True
        user.save(update_fields=["is_active"])
        record_audit(
            actor=request.user,
            action="user.activated",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.id == request.user.id:
            raise ValidationError({"detail": "You cannot deactivate your own account."})
        user.is_active = False
        user.save(update_fields=["is_active"])
        record_audit(
            actor=request.user,
            action="user.deactivated",
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        return Response(self.get_serializer(user).data)