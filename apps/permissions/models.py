"""Permission model for module-level access control.

Permissions are stored in the database and checked server-side on every
protected endpoint. They are deliberately simple: a user either has a
permission code or not. Admin access is also modeled here so the whole
permission surface is uniform and manageable from the admin panel.

Permission codes:
    BULLDROP_ACCESS   - access to the BullDrop module
    INTERNLIK_ACCESS  - access to the Internlik module
    ADMIN_ACCESS      - access to the admin panel and user management
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

BULLDROP_ACCESS = "BULLDROP_ACCESS"
INTERNLIK_ACCESS = "INTERNLIK_ACCESS"
ADMIN_ACCESS = "ADMIN_ACCESS"

ALL_PERMISSION_CODES = (BULLDROP_ACCESS, INTERNLIK_ACCESS, ADMIN_ACCESS)

PERMISSION_LABELS = {
    BULLDROP_ACCESS: "BullDrop access",
    INTERNLIK_ACCESS: "Internlik access",
    ADMIN_ACCESS: "Admin access",
}


class Permission(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    code = models.CharField(max_length=32, db_index=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_permissions",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "code"], name="unique_user_permission"),
        ]
        indexes = [models.Index(fields=["user", "code"])]
        ordering = ["code"]

    def __str__(self):
        return f"{self.user_id} : {self.code}"