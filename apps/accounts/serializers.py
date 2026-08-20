from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "name", "password", "password_confirm", "timezone")

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class UserSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    timezone = serializers.CharField()

    class Meta:
        model = User
        fields = ("id", "email", "name", "timezone", "date_joined", "permissions")
        read_only_fields = fields

    def get_permissions(self, obj) -> list[str]:
        return sorted(obj.permission_codes())


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, style={"input_type": "password"})
    new_password = serializers.CharField(min_length=10, max_length=128, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password(value)
        return value


class ProfileUpdateSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ("name", "timezone")
        extra_kwargs = {"name": {"required": False, "allow_blank": True}}

    def update(self, instance, validated_data):
        if "timezone" in validated_data:
            instance.timezone = validated_data["timezone"]
            validated_data.pop("timezone")
        return super().update(instance, validated_data)