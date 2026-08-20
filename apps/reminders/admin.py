from django.contrib import admin

from .models import Reminder


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "remind_at", "recurrence", "completed")
    list_filter = ("recurrence", "completed")
    search_fields = ("title", "user__email")