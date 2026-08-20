from django.contrib import admin

from .models import BullDropAccount, BullDropClaim


@admin.register(BullDropAccount)
class BullDropAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "username", "created_at")
    search_fields = ("name", "username", "user__email")


@admin.register(BullDropClaim)
class BullDropClaimAdmin(admin.ModelAdmin):
    list_display = ("account", "claimed_at", "promo_code", "note")
    list_filter = ("claimed_at",)
    search_fields = ("promo_code", "account__name")