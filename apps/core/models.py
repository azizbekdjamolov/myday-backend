"""Audit trail for sensitive operations.

Records who did what, when. Never stores secret values, only metadata
(action, resource, outcome). Consumers can render timeline views; the data is
not part of any API response by default.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        VAULT_ITEM_CREATED = "vault_item.created", "Vault item created"
        VAULT_ITEM_UPDATED = "vault_item.updated", "Vault item updated"
        VAULT_ITEM_DELETED = "vault_item.deleted", "Vault item deleted"
        VAULT_REVEALED = "vault.revealed", "Vault secret revealed"
        VAULT_REVEAL_FAILED = "vault.reveal_failed", "Vault reveal failed"
        VAULT_FILE_UPLOADED = "vault.file.uploaded", "Vault file uploaded"
        VAULT_FILE_DOWNLOADED = "vault.file.downloaded", "Vault file downloaded"
        VAULT_FILE_DELETED = "vault.file.deleted", "Vault file deleted"
        BULLDROP_CLAIMED = "bulldrop.claimed", "BullDrop reward claimed"
        BULLDROP_CLAIM_REJECTED = "bulldrop.claim_rejected", "BullDrop claim rejected"
        AUTH_LOGIN = "auth.login", "Login"
        AUTH_LOGIN_FAILED = "auth.login_failed", "Login failed"
        AUTH_LOGOUT = "auth.logout", "Logout"
        AUTH_REGISTER = "auth.register", "Registration"
        PERMISSION_GRANTED = "permission.granted", "Permission granted"
        PERMISSION_REVOKED = "permission.revoked", "Permission revoked"
        USER_ACTIVATED = "user.activated", "User activated"
        USER_DEACTIVATED = "user.deactivated", "User deactivated"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    action = models.CharField(max_length=64, db_index=True, choices=Action.choices)
    resource_type = models.CharField(max_length=32, blank=True, default="")
    resource_id = models.CharField(max_length=64, blank=True, default="")
    outcome = models.CharField(max_length=16, default="success", choices=[("success", "success"), ("failure", "failure")])
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["actor", "action", "-created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.actor_id} at {self.created_at:%Y-%m-%d %H:%M:%S}"


def record_audit(
    *,
    actor,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    outcome: str = "success",
    metadata: dict | None = None,
    request=None,
) -> AuditLog:
    """Create an audit entry. ``metadata`` must never contain secrets."""
    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = _client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:512]
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id)[:64],
        outcome=outcome,
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return getattr(request, "META", {}).get("REMOTE_ADDR", None)