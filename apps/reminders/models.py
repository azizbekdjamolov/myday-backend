"""Personal reminders.

Supports one-time, daily, weekly and custom-interval recurrence. ``remind_at``
always holds the *next* scheduled occurrence; completing a recurring reminder
advances it to the following occurrence, completing a one-time reminder closes
it permanently.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.timezone import localtime

RECURRENCE_CHOICES = [
    ("once", "One-time"),
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("custom", "Custom"),
]


class Reminder(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminders")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    remind_at = models.DateTimeField()
    recurrence = models.CharField(max_length=16, choices=RECURRENCE_CHOICES, default="once")
    interval_days = models.PositiveIntegerField(default=1)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["remind_at"]
        indexes = [models.Index(fields=["user", "completed", "remind_at"])]

    def __str__(self):
        return f"{self.title} @ {self.remind_at:%Y-%m-%d %H:%M}"

    @property
    def repeats(self) -> bool:
        return self.recurrence != "once"

    def next_remind_at(self, reference: dt.datetime | None = None) -> dt.datetime:
        """Next concrete occurrence time (aware, user tz)."""
        tz = self.user.timezone
        now = reference or timezone.now()
        now = now.astimezone(tz)
        remind = self.remind_at
        if remind.tzinfo is None:
            remind = remind.replace(tzinfo=dt.timezone.utc)
        remind = remind.astimezone(tz)

        if not self.repeats or remind > now:
            return remind

        if self.recurrence == "daily":
            days = 1
        elif self.recurrence == "weekly":
            days = 7
        else:  # custom
            days = max(1, self.interval_days)

        delta = dt.timedelta(days=days)
        while remind <= now:
            remind += delta
        return remind

    def is_due(self, now: dt.datetime | None = None) -> bool:
        """An uncompleted occurrence has passed (recurring reminders stay due
        until completed, then are rescheduled to the next occurrence)."""
        now = now or timezone.now()
        return not self.completed and self.remind_at <= now


def advance_after_complete(reminder: Reminder) -> Reminder:
    """Handle the 'completed' action.

    Recurring reminders are rescheduled to their next occurrence (and
    un-completed); one-time reminders stay completed.
    """
    if reminder.repeats:
        reminder.remind_at = reminder.next_remind_at()
        reminder.completed = False
        reminder.save(update_fields=["remind_at", "completed"])
    else:
        reminder.completed = True
        reminder.save(update_fields=["completed"])
    return reminder