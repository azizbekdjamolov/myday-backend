from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import User
from apps.permissions.models import PERMISSION_LABELS


class AdminUserSerializer(serializers.ModelSerializer):
    """Basic user information for the admin panel.

    Deliberately excludes everything sensitive: no vault data, no passwords,
    no token state. Just identity + status + permissions.
    """

    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "name", "is_active", "date_joined", "permissions")
        read_only_fields = fields

    def get_permissions(self, obj):
        return sorted(obj.permission_codes())


class PermissionChangeSerializer(serializers.Serializer):
    permission = serializers.ChoiceField(
        choices=[(code, label) for code, label in PERMISSION_LABELS.items() if code != "ADMIN_ACCESS"]
    )
    action = serializers.ChoiceField(choices=["grant", "revoke"])