from django.contrib import admin

from .models import ClassSchedule


@admin.register(ClassSchedule)
class ClassScheduleAdmin(admin.ModelAdmin):
    list_display = ("group_name", "user", "is_recurring", "days_of_week", "start_time", "specific_date")
    list_filter = ("is_recurring",)
    search_fields = ("group_name", "user__email")