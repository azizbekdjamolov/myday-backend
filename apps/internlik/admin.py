from django.contrib import admin

from .models import InternlikEntry


@admin.register(InternlikEntry)
class InternlikEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "status", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "body", "user__email")