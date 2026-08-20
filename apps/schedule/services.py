"""Helpers to compute schedule state for serializers and the dashboard.

All computations happen server-side in the user's timezone so the browser
clock is never trusted.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from django.utils.timezone import localtime


def remaining_seconds(occurrence: dt.datetime, now: dt.datetime | None = None) -> int:
    now = now or timezone.now()
    delta = occurrence - now
    return max(0, int(delta.total_seconds()))


def class_state(schedule, now: dt.datetime | None = None):
    """Build the serialized representation of a class including timing state."""
    now = now or timezone.now()
    occurrence = schedule.next_occurrence()
    if occurrence is None:
        return {"status": "completed", "next_at": None, "remaining_seconds": 0, "reminder_at": None}

    tz = schedule.user.timezone
    now_local = localtime(now, timezone=tz)

    if remaining_seconds(occurrence) == 0:
        status = "completed"
    elif occurrence.date() == now_local.date():
        status = "today"
    else:
        status = "upcoming"

    return {
        "status": status,
        "next_at": occurrence.isoformat(),
        "remaining_seconds": remaining_seconds(occurrence, now),
        "reminder_at": schedule.next_reminder_at().isoformat() if schedule.next_reminder_at() else None,
    }


def next_class_for_user(user, now: dt.datetime | None = None) -> dict | None:
    """The single most imminent class for the dashboard."""
    now = now or timezone.now()
    best = None
    best_occurrence = None
    for schedule in user.classes.all():
        occurrence = schedule.next_occurrence()
        if occurrence is None:
            continue
        if best_occurrence is None or occurrence < best_occurrence:
            best = schedule
            best_occurrence = occurrence
    if best is None:
        return None
    state = class_state(best, now)
    state["id"] = best.id
    state["group_name"] = best.group_name
    state["start_time"] = best.start_time.strftime("%H:%M")
    state["reminder_minutes"] = best.reminder_minutes
    return state