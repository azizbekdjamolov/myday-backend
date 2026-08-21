from __future__ import annotations

from rest_framework import serializers

from .models import BullDropAccount


class BullDropAccountSerializer(serializers.ModelSerializer):
    browser_display = serializers.CharField(source="get_browser_display", read_only=True)

    class Meta:
        model = BullDropAccount
        fields = ("id", "name", "username", "browser", "browser_display", "notes", "created_at")
        read_only_fields = ("id", "created_at", "browser_display")


class BullDropAccountStatusSerializer(BullDropAccountSerializer):
    status = serializers.CharField(read_only=True)
    next_available_at = serializers.DateTimeField(read_only=True)
    remaining_seconds = serializers.IntegerField(read_only=True)
    last_claim_at = serializers.SerializerMethodField()

    class Meta(BullDropAccountSerializer.Meta):
        fields = BullDropAccountSerializer.Meta.fields + (
            "status",
            "next_available_at",
            "remaining_seconds",
            "last_claim_at",
        )
        read_only_fields = fields

    def get_last_claim_at(self, obj):
        last = obj.last_claim
        return last.claimed_at.isoformat() if last else None
