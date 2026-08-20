from __future__ import annotations

from rest_framework import serializers

from .models import ClassSchedule
from .services import class_state


class ClassScheduleSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    next_at = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    reminder_at = serializers.SerializerMethodField()

    class Meta:
        model = ClassSchedule
        fields = (
            "id",
            "group_name",
            "days_of_week",
            "start_time",
            "reminder_minutes",
            "is_recurring",
            "specific_date",
            "created_at",
            "status",
            "next_at",
            "remaining_seconds",
            "reminder_at",
        )
        read_only_fields = ("id", "created_at")

    def _state(self, obj):
        return class_state(obj)

    def get_status(self, obj):
        return self._state(obj)["status"]

    def get_next_at(self, obj):
        return self._state(obj)["next_at"]

    def get_remaining_seconds(self, obj):
        return self._state(obj)["remaining_seconds"]

    def get_reminder_at(self, obj):
        return self._state(obj)["reminder_at"]

    def validate(self, attrs):
        is_recurring = attrs.get("is_recurring", self.instance.is_recurring if self.instance else True)
        if is_recurring and not attrs.get("days_of_week"):
            raise serializers.ValidationError({"days_of_week": "Select at least one day for a recurring class."})
        if not is_recurring and not attrs.get("specific_date"):
            raise serializers.ValidationError({"specific_date": "A one-time class requires a date."})
        return attrs