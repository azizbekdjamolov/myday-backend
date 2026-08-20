from django.contrib import admin

from .models import Permission


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "granted_at", "granted_by")
    list_filter = ("code",)
    search_fields = ("user__email", "code")
    readonly_fields = ("granted_at",)