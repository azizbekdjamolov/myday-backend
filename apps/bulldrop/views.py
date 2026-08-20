from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.exceptions import ConflictError
from apps.core.models import record_audit
from apps.permissions.permissions import HasBullDropAccess

from .models import BullDropAccount, BullDropClaim
from .serializers import (
    BullDropAccountSerializer,
    BullDropAccountStatusSerializer,
    BullDropClaimSerializer,
)


class BullDropAccountViewSet(viewsets.ModelViewSet):
    """BullDrop accounts. Only visible to users with BullDrop access."""

    permission_classes = [HasBullDropAccess]

    def get_serializer_class(self):
        # List AND detail always include the live status/countdown fields.
        if self.action in ("list", "retrieve"):
            return BullDropAccountStatusSerializer
        return BullDropAccountSerializer

    def get_queryset(self):
        return BullDropAccount.objects.filter(user=self.request.user).prefetch_related("claims")

    def perform_create(self, serializer):
        account = serializer.save(user=self.request.user)
        record_audit(
            actor=self.request.user,
            action="bulldrop.account.created",
            resource_type="bulldrop_account",
            resource_id=account.id,
            request=self.request,
        )

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        """Server-authoritative claim.

        Rejects claims when the account is not ready or when the account does
        not belong to the authenticated user. The ready state is recomputed
        from the stored claim timestamp + cooldown, so a client that tampered
        with its local clock gains nothing.
        """
        account = self.get_object()
        if account.status != "ready":
            raise ConflictError("This account's reward is not ready yet.")

        promo_code = (request.data.get("promo_code") or "").strip()[:64]
        note = (request.data.get("note") or "").strip()[:300]

        claim = BullDropClaim.objects.create(account=account, promo_code=promo_code, note=note)
        record_audit(
            actor=request.user,
            action="bulldrop.claimed",
            resource_type="bulldrop_account",
            resource_id=account.id,
            metadata={"promo_code": promo_code if promo_code else None},
            request=request,
        )
        account.refresh_from_db()  # drop prefetched claims cache so status is current
        payload = BullDropAccountStatusSerializer(account).data
        payload["claim"] = BullDropClaimSerializer(claim).data
        return Response(payload, status=status.HTTP_201_CREATED)


class BullDropClaimViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasBullDropAccess]
    serializer_class = BullDropClaimSerializer

    def get_queryset(self):
        queryset = BullDropClaim.objects.filter(account__user=self.request.user).select_related("account")
        promo = self.request.query_params.get("promo", "").strip()
        if promo:
            queryset = queryset.filter(promo_code__icontains=promo)
        return queryset

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Ready/waiting counts for the BullDrop dashboard header."""
        accounts = BullDropAccount.objects.filter(user=request.user)
        ready = sum(1 for a in accounts if a.status == "ready")
        waiting = accounts.count() - ready
        return Response({"ready": ready, "waiting": waiting})