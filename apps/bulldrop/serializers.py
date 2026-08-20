from __future__ import annotations

from rest_framework import serializers

from .models import BullDropAccount, BullDropClaim


class BullDropAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BullDropAccount
        fields = ("id", "name", "username", "notes", "created_at")
        read_only_fields = ("id", "created_at")


class BullDropAccountStatusSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    next_available_at = serializers.DateTimeField(read_only=True)
    remaining_seconds = serializers.IntegerField(read_only=True)
    last_claim_at = serializers.SerializerMethodField()

    class Meta:
        model = BullDropAccount
        fields = (
            "id",
            "name",
            "username",
            "notes",
            "created_at",
            "status",
            "next_available_at",
            "remaining_seconds",
            "last_claim_at",
        )
        read_only_fields = fields

    def get_last_claim_at(self, obj):
        last = obj.last_claim
        return last.claimed_at.isoformat() if last else None


class BullDropClaimSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = BullDropClaim
        fields = ("id", "account", "account_name", "claimed_at", "promo_code", "note")
        read_only_fields = ("id", "account_name", "claimed_at")

    def validate(self, attrs):
        account = attrs["account"]
        if account.user_id != self.context["request"].user.id:
            raise serializers.ValidationError({"account": "You do not own this account."})
        if account.status != "ready":
            raise serializers.ValidationError({"account": "This account's reward is not ready yet."})
        return attrs