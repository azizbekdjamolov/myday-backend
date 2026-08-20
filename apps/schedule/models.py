"""Class schedule model.

Designed for the single job it exists to do: remember when a class happens.
No subjects, teachers, homework or grades — just group name, day(s), time and
an optional reminder offset.

Two kinds of class:

* Recurring — weekly on one or more days (``is_recurring=True``,
  ``days_of_week`` set, ``specific_date`` empty).
* One-time — a single occurrence on ``specific_date`` (``is_recurring=False``).
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.timezone import localtime

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

VALID_DAYS = (0, 1, 2, 3, 4, 5, 6)


class ClassSchedule(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classes")
    group_name = models.CharField(max_length=120)
    days_of_week = models.JSONField(default=list, blank=True)
    start_time = models.TimeField()
    reminder_minutes = models.PositiveIntegerField(default=60)
    is_recurring = models.BooleanField(default=True)
    specific_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_recurring", "start_time"]
        verbose_name_plural = "class schedules"

    def __str__(self):
        return f"{self.group_name} @ {self.start_time:%H:%M}"

    # -- occurrence math ------------------------------------------------------

    def _user_now(self) -> dt.datetime:
        return localtime(timezone.now(), timezone=self.user.timezone)

    def next_occurrence(self, reference: dt.datetime | None = None) -> dt.datetime | None:
        """Return the next concrete datetime of this class (aware, user tz)."""
        tz = self.user.timezone
        now = reference or self._user_now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.timezone.utc).astimezone(tz)
        else:
            now = now.astimezone(tz)

        start = dt.datetime.combine(now.date(), self.start_time, tzinfo=tz)

        if not self.is_recurring:
            if self.specific_date is None:
                return None
            occurrence = dt.datetime.combine(self.specific_date, self.start_time, tzinfo=tz)
            return occurrence if occurrence >= now else None

        days = sorted({int(d) for d in self.days_of_week if d in VALID_DAYS})
        if not days:
            return None

        # Today's class already started -> advance to next scheduled day.
        if now.weekday() in days and start >= now:
            return start
        for offset in range(1, 8):
            candidate = now + dt.timedelta(days=offset)
            if candidate.weekday() in days:
                return dt.datetime.combine(candidate.date(), self.start_time, tzinfo=tz)
        return None

    def next_reminder_at(self, reference: dt.datetime | None = None) -> dt.datetime | None:
        occurrence = self.next_occurrence(reference)
        if occurrence is None:
            return None
        return occurrence - dt.timedelta(minutes=self.reminder_minutes)

    def is_completed(self, reference: dt.datetime | None = None) -> bool:
        """True when the most relevant upcoming occurrence has already passed."""
        if self.is_recurring:
            return False  # recurring classes are never permanently "completed"
        occurrence = self.next_occurrence(reference)
        return occurrence is None