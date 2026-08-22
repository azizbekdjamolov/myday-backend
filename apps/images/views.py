"""Images API views.

Security invariants:

- Ownership is always derived from the authenticated session
  (``request.user``); any client-supplied owner id is ignored. Foreign or
  missing resources return 404 without distinguishing "exists elsewhere".
- Image bytes are served only by the ``view`` action after the per-image
  password check succeeds. There is no permanent URL; the response is a
  one-off body stream to the already-authenticated caller.
- Uploads are validated server-side (size + magic bytes); storage keys are
  random and never client-influenced, which rules out path traversal.
- Password values are never logged; audit entries carry metadata only.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.models import record_audit

from .models import Image
from .serializers import (
    ImagePasswordSerializer,
    ImageRenameSerializer,
    ImageSerializer,
    ImageUploadSerializer,
)
from . import services


class ImageViewThrottle(UserRateThrottle):
    """Brute-force guard on password verification attempts (per user)."""

    scope = "image_view"


class ImageViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = ImageSerializer

    # Every query is scoped to the authenticated owner — user isolation.
    def get_queryset(self):
        queryset = Image.objects.filter(owner=self.request.user)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return ImageUploadSerializer
        if self.action in ("partial_update", "update"):
            return ImageRenameSerializer
        return ImageSerializer

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        data = file_obj.read()

        try:
            key, sha256 = services.store_image_bytes(data=data)
        except Exception:
            raise ValidationError({"file": "Image could not be stored."})

        name = (serializer.validated_data.get("name") or "").strip() or (file_obj.name or "").rsplit(".", 1)[0][:100]
        image = Image.objects.create(
            owner=request.user,
            name=name or "image",
            storage_key=key,
            # Verified from magic bytes at validation time — never the
            # client-declared MIME type.
            content_type=serializer.validated_data["verified_content_type"],
            size=len(data),
            sha256=sha256,
        )
        image.set_image_password(serializer.validated_data["password"])
        image.save(update_fields=["password_hash"])

        record_audit(
            actor=request.user,
            action="image.uploaded",
            resource_type="image",
            resource_id=image.id,
            request=request,
        )
        return Response(ImageSerializer(image).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        image = self.get_object()
        serializer = self.get_serializer(image, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit(
            actor=request.user,
            action="image.renamed",
            resource_type="image",
            resource_id=image.id,
            request=request,
        )
        return Response(ImageSerializer(image).data)

    def destroy(self, request, *args, **kwargs):
        image = self.get_object()
        services.delete_image_file(image.storage_key)
        record_audit(
            actor=request.user,
            action="image.deleted",
            resource_type="image",
            resource_id=image.id,
            request=request,
        )
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Password-gated viewing
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], throttle_classes=[ImageViewThrottle])
    def view(self, request, pk=None):
        image = self.get_object()
        serializer = ImagePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not image.check_image_password(serializer.validated_data["password"]):
            record_audit(
                actor=request.user,
                action="image.view_failed",
                resource_type="image",
                resource_id=image.id,
                outcome="failure",
                request=request,
            )
            # Deliberately vague: nothing about the image is revealed.
            raise PermissionDenied("Incorrect password.")

        try:
            data = services.open_image_bytes(image.storage_key)
        except Exception:
            raise PermissionDenied("Image is no longer available.")

        record_audit(
            actor=request.user,
            action="image.viewed",
            resource_type="image",
            resource_id=image.id,
            request=request,
        )
        response = HttpResponse(data, content_type=image.content_type)
        # Inline so an <img>/blob consumer can render it, but never cached and
        # never discoverable via a permanent URL.
        response["Cache-Control"] = "no-store"
        response["Content-Disposition"] = 'inline'
        return response
