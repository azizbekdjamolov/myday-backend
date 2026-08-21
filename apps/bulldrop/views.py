from __future__ import annotations

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.exceptions import ConflictError
from apps.core.models import record_audit
from apps.permissions.permissions import HasBullDropAccess

from .models import BullDropAccount, BullDropClaim
from .serializers import BullDropAccountSerializer, BullDropAccountStatusSerializer


class BullDropAccountViewSet(viewsets.ModelViewSet):
    """BullDrop accounts. Only visible to users with BullDrop access."""

    permission_classes = [HasBullDropAccess]

    def get_serializer_class(self):
        # List AND detail always include the live status/countdown fields;
        # writes use the editable serializer.
        if self.action in ("list", "retrieve"):
            return BullDropAccountStatusSerializer
        return BullDropAccountSerializer

    def get_queryset(self):
        queryset = (
            BullDropAccount.objects.filter(user=self.request.user)
            .prefetch_related("claims")
        )
        params = self.request.query_params
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(username__icontains=search))
        browser = params.get("browser", "").strip()
        if browser:
            queryset = queryset.filter(browser=browser)
        # Status is derived from the server-side claim timer, so ready/waiting
        # is resolved through the same model property the API reports.
        account_status = params.get("status", "").strip()
        if account_status in ("ready", "waiting"):
            matching = [a.id for a in queryset if a.status == account_status]
            queryset = queryset.filter(id__in=matching)
        return queryset

    def perform_create(self, serializer):
        account = serializer.save(user=self.request.user)
        record_audit(
            actor=self.request.user,
            action="bulldrop.account.created",
            resource_type="bulldrop_account",
            resource_id=account.id,
            request=self.request,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Ready/waiting counts for the BullDrop dashboard header."""
        accounts = BullDropAccount.objects.filter(user=request.user)
        ready = sum(1 for a in accounts if a.status == "ready")
        waiting = accounts.count() - ready
        return Response({"total": accounts.count(), "ready": ready, "waiting": waiting})

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        """Server-authoritative one-click claim.

        Rejects claims when the account is not ready or when the account does
        not belong to the authenticated user. The ready state is recomputed
        from the stored claim timestamp + cooldown, so a client that tampered
        with its local clock gains nothing.
        """
        account = self.get_object()
        if account.status != "ready":
            raise ConflictError("This account's reward is not ready yet.")

        claim = BullDropClaim.objects.create(account=account)
        record_audit(
            actor=request.user,
            action="bulldrop.claimed",
            resource_type="bulldrop_account",
            resource_id=account.id,
            request=request,
        )
        account.refresh_from_db()  # drop prefetched claims cache so status is current
        payload = BullDropAccountStatusSerializer(account).data
        payload["claim"] = {"id": claim.id, "account": account.id, "claimed_at": claim.claimed_at.isoformat()}
        return Response(payload, status=status.HTTP_201_CREATED)
