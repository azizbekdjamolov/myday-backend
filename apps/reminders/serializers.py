from __future__ import annotations

from rest_framework import serializers

from .models import RECURRENCE_CHOICES, Reminder
from .models import advance_after_complete


class ReminderSerializer(serializers.ModelSerializer):
    next_at = serializers.SerializerMethodField()
    is_due = serializers.SerializerMethodField()

    class Meta:
        model = Reminder
        fields = (
            "id",
            "title",
            "description",
            "remind_at",
            "recurrence",
            "interval_days",
            "completed",
            "created_at",
            "next_at",
            "is_due",
        )
        read_only_fields = ("id", "created_at")

    def get_next_at(self, obj):
        return obj.next_remind_at().isoformat()

    def get_is_due(self, obj):
        return obj.is_due()

    def validate(self, attrs):
        if attrs.get("recurrence", "once") == "custom":
            interval = attrs.get("interval_days", 1)
            if not interval or interval < 1:
                raise serializers.ValidationError({"interval_days": "Must be at least 1 day."})
        elif "interval_days" in attrs:
            attrs.pop("interval_days")
        return attrs


class ReminderCompleteSerializer(serializers.Serializer):
    """Empty body marker; just confirms the intent to complete a reminder."""

    pass