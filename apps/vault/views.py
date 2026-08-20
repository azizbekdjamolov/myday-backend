"""Vault API views.

Every query is scoped to ``request.user``; no client-supplied user id is ever
trusted. Reveal requires the current vault password (re-authentication) AND an
active unlock session (auto-locked by TTL). File downloads are gated by
ownership and served from private storage only.
"""

from __future__ import annotations

import datetime as dt
import time

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from apps.core.models import record_audit
from apps.core.storage import NotFound as BlobNotFound

from .models import VaultFile, VaultItem
from .serializers import (
    ChangeVaultPasswordSerializer,
    UnlockSerializer,
    VaultFileSerializer,
    VaultItemCreateSerializer,
    VaultItemSerializer,
    VaultRevealResponseSerializer,
    VaultRevealSerializer,
)
from . import services


class VaultItemViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "vault_reveal"

    def get_serializer_class(self):
        if self.action in ("create", "partial_update", "update"):
            return VaultItemCreateSerializer
        return VaultItemSerializer

    def get_queryset(self):
        queryset = VaultItem.objects.filter(user=self.request.user).prefetch_related("files")
        search = self.request.query_params.get("search", "").strip()
        if search:
            # Titles are searchable in SQL; usernames/notes are encrypted so we
            # match them in Python after decrypting (small personal dataset).
            sql_hits = set(queryset.filter(title__icontains=search).values_list("id", flat=True))
            decrypted_hits = set()
            for item in queryset:
                username = services.decrypt_field(item.encrypted_username)
                notes = services.decrypt_field(item.encrypted_notes)
                if username and search.lower() in username.lower():
                    decrypted_hits.add(item.id)
                elif notes and search.lower() in notes.lower():
                    decrypted_hits.add(item.id)
            ids = sql_hits | decrypted_hits
            queryset = queryset.filter(id__in=ids)
        category = self.request.query_params.get("category", "").strip()
        if category:
            queryset = queryset.filter(category=category)
        return queryset

    def perform_create(self, serializer):
        item = serializer.save(user=self.request.user)
        record_audit(
            actor=self.request.user,
            action="vault_item.created",
            resource_type="vault_item",
            resource_id=item.id,
            request=self.request,
        )

    def perform_update(self, serializer):
        item = serializer.save()
        record_audit(
            actor=self.request.user,
            action="vault_item.updated",
            resource_type="vault_item",
            resource_id=item.id,
            request=self.request,
        )

    def perform_destroy(self, instance):
        services.delete_item_files(self.request.user, instance)
        record_audit(
            actor=self.request.user,
            action="vault_item.deleted",
            resource_type="vault_item",
            resource_id=instance.id,
            request=self.request,
        )
        instance.delete()

    @action(detail=True, methods=["post"], throttle_classes=[ScopedRateThrottle])
    def reveal(self, request, pk=None):
        item = self.get_object()
        serializer = VaultRevealSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not services.is_unlocked(request.user):
            raise PermissionDenied("Vault is locked. Unlock it first.")

        password = serializer.validated_data["password"]
        if not request.user.check_password(password):
            record_audit(
                actor=request.user,
                action="vault.reveal_failed",
                resource_type="vault_item",
                resource_id=item.id,
                outcome="failure",
                request=request,
            )
            raise PermissionDenied("Password incorrect.")

        services.unlock(request.user)
        record_audit(
            actor=request.user,
            action="vault.revealed",
            resource_type="vault_item",
            resource_id=item.id,
            request=request,
        )
        payload = {
            "username": services.decrypt_field(item.encrypted_username),
            "password": services.decrypt_field(item.encrypted_password),
            "notes": services.decrypt_field(item.encrypted_notes),
        }
        return Response(VaultRevealResponseSerializer(payload).data)


class VaultFileViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        return VaultFileSerializer

    def get_queryset(self):
        return VaultFile.objects.filter(user=self.request.user).select_related("vault_item")

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        if file_obj is None:
            raise ValidationError({"file": "A file is required."})
        if file_obj.size > settings.VAULT_FILE_MAX_SIZE:
            raise ValidationError({"file": f"File exceeds the {settings.VAULT_FILE_MAX_SIZE} byte limit."})

        vault_item_id = request.data.get("vault_item") or None
        vault_item = None
        if vault_item_id:
            vault_item = VaultItem.objects.filter(user=request.user, id=vault_item_id).first()
            if vault_item is None:
                raise PermissionDenied("You do not own that vault item.")

        key, sha256, _ = services.store_vault_file(
            user=request.user,
            data=file_obj.read(),
            filename=file_obj.name,
            content_type=getattr(file_obj, "content_type", "") or "",
        )
        instance = VaultFile.objects.create(
            user=request.user,
            vault_item=vault_item,
            filename=file_obj.name[:255],
            content_type=getattr(file_obj, "content_type", "") or "",
            size=file_obj.size,
            sha256=sha256,
            storage_key=key,
        )
        record_audit(
            actor=request.user,
            action="vault.file.uploaded",
            resource_type="vault_file",
            resource_id=instance.id,
            request=request,
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        services.delete_vault_file(instance)
        record_audit(
            actor=request.user,
            action="vault.file.deleted",
            resource_type="vault_file",
            resource_id=instance.id,
            request=request,
        )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        file_obj = self.get_object()
        try:
            data = services.open_vault_file(file_obj)
        except BlobNotFound:
            raise PermissionDenied("File is no longer available.")
        record_audit(
            actor=request.user,
            action="vault.file.downloaded",
            resource_type="vault_file",
            resource_id=file_obj.id,
            request=request,
        )
        response = HttpResponse(data, content_type=file_obj.content_type or "application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{file_obj.filename}"'
        return response


class VaultStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        expires = services.unlock_expiry(request.user)
        unlocked = expires > time.time()
        return Response(
            {
                "unlocked": unlocked,
                "expires_at": timezone.datetime.fromtimestamp(expires, tz=dt.timezone.utc).isoformat() if unlocked else None,
                "autolock_minutes": settings.VAULT_AUTOLOCK_MINUTES,
            }
        )

    def post(self, request):
        action = request.query_params.get("action", "unlock")
        if action == "lock":
            services.lock(request.user)
            return Response({"unlocked": False, "expires_at": None})

        serializer = UnlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["password"]):
            raise PermissionDenied("Password incorrect.")
        expires = services.unlock(request.user)
        return Response(
            {
                "unlocked": True,
                "expires_at": timezone.datetime.fromtimestamp(expires, tz=dt.timezone.utc).isoformat(),
                "autolock_minutes": settings.VAULT_AUTOLOCK_MINUTES,
            }
        )


class VaultPasswordView(APIView):
    """Re-authenticated change of the user's own vault access password.

    This changes the account password (the only secret protecting the vault).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangeVaultPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["current_password"]):
            raise PermissionDenied("Current password incorrect.")
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        services.lock(request.user)
        return Response({"detail": "Password updated. Please sign in again."})