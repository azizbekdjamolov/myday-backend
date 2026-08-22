"""Serializers for the private Images module.

List/detail payloads expose metadata only: id, name, size, content type and
timestamps. ``storage_key`` and ``password_hash`` are never serialised and no
permanent URL of any kind is included — bytes flow exclusively through the
password-verified view action.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import NAME_MAX_LENGTH, Image
from .validation import validate_upload


class ImageSerializer(serializers.ModelSerializer):
    """Metadata serializer — safe for lists and details."""

    class Meta:
        model = Image
        fields = ("id", "name", "content_type", "size", "created_at", "updated_at")
        read_only_fields = fields


class ImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=NAME_MAX_LENGTH,
    )
    password = serializers.CharField(min_length=4, max_length=128, style={"input_type": "password"}, write_only=True)
    confirm_password = serializers.CharField(style={"input_type": "password"}, write_only=True)

    def validate_file(self, file_obj):
        limit = settings.IMAGE_MAX_SIZE
        if file_obj.size <= 0:
            raise serializers.ValidationError("A non-empty image file is required.")
        if file_obj.size > limit:
            raise serializers.ValidationError("Image exceeds the maximum allowed size.")
        return file_obj

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        file_obj = attrs["file"]
        data = file_obj.read()
        try:
            # Content sniffing: extension/declared MIME are never trusted.
            content_type, _ext = validate_upload(data=data, declared_name=file_obj.name or "")
        except Exception:
            raise serializers.ValidationError({"file": "Unsupported image type. Use JPG, JPEG, PNG or WEBP."})
        finally:
            file_obj.seek(0)
        # Store the *verified* type derived from magic bytes.
        attrs["verified_content_type"] = content_type
        return attrs


class ImageRenameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ("name",)

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name must not be empty.")
        return value[:NAME_MAX_LENGTH]


class ImagePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, style={"input_type": "password"}, write_only=True)
