from django.contrib import admin

from .models import BullDropAccount, BullDropClaim


@admin.register(BullDropAccount)
class BullDropAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "username", "browser", "created_at")
    list_filter = ("browser",)
    search_fields = ("name", "username", "user__email")


@admin.register(BullDropClaim)
class BullDropClaimAdmin(admin.ModelAdmin):
    list_display = ("account", "claimed_at")
    list_filter = ("claimed_at",)
    search_fields = ("account__name",)
