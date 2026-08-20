from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import VaultFile, VaultItem


class VaultItemSerializer(serializers.ModelSerializer):
    """List/CRUD serializer — NEVER exposes decrypted sensitive values."""

    has_username = serializers.BooleanField(read_only=True)
    has_password = serializers.BooleanField(read_only=True)
    has_notes = serializers.BooleanField(read_only=True)
    file_count = serializers.SerializerMethodField()

    class Meta:
        model = VaultItem
        fields = (
            "id",
            "category",
            "title",
            "has_username",
            "has_password",
            "has_notes",
            "file_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_file_count(self, obj):
        return obj.files.count()


class VaultItemCreateSerializer(serializers.ModelSerializer):
    """Write serializer that accepts plaintext and encrypts it at the DB."""

    username = serializers.CharField(required=False, allow_blank=True, max_length=512)
    password = serializers.CharField(required=False, allow_blank=True, max_length=512)
    notes = serializers.CharField(required=False, allow_blank=True, style={"base_template": "textarea.html"})

    class Meta:
        model = VaultItem
        fields = ("id", "category", "title", "username", "password", "notes")

    def validate(self, attrs):
        if not attrs.get("title"):
            raise serializers.ValidationError({"title": "Title is required."})
        return attrs

    def create(self, validated_data):
        validated_data["encrypted_username"] = validated_data.pop("username", "") or ""
        validated_data["encrypted_password"] = validated_data.pop("password", "") or ""
        validated_data["encrypted_notes"] = validated_data.pop("notes", "") or ""
        return VaultItem.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for field in ("username", "password", "notes"):
            value = validated_data.pop(field, None)
            if value is not None:
                setattr(instance, f"encrypted_{field}", value)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class VaultRevealSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class VaultRevealResponseSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class VaultFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = VaultFile
        fields = ("id", "vault_item", "filename", "content_type", "size", "created_at")
        read_only_fields = ("id", "size", "created_at")


class UnlockSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class ChangeVaultPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, style={"input_type": "password"})
    new_password = serializers.CharField(min_length=10, max_length=128, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password(value)
        return value