from __future__ import annotations

from rest_framework import serializers

from .models import InternlikEntry


class InternlikEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = InternlikEntry
        fields = ("id", "kind", "title", "body", "status", "deadline", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")