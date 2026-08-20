from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "outcome", "resource_type", "resource_id")
    list_filter = ("action", "outcome")
    search_fields = ("resource_id", "metadata")
    readonly_fields = ("created_at", "actor", "action", "outcome", "metadata", "ip_address", "user_agent")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False