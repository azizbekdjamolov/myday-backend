"""Reminder tests: recurrence, completion, ownership."""

from __future__ import annotations

import datetime as dt
from unittest import mock

from django.utils import timezone

from apps.reminders.models import Reminder

from tests.conftest import PASSWORD

REMINDERS = "/api/v1/reminders/"


def _login(api, user):
    response = api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    csrf = api.cookies.get("myday_csrftoken")
    if csrf is not None:
        api.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


def test_create_one_time_reminder(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        REMINDERS,
        {
            "title": "Push project to GitHub",
            "description": "before class",
            "remind_at": "2026-08-25T17:00:00Z",
            "recurrence": "once",
        },
        format="json",
    )
    assert response.status_code == 201
    reminder = Reminder.objects.get(user=normal_user)
    assert reminder.title == "Push project to GitHub"


def test_daily_reminder_advances_after_complete(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    now = timezone.now()
    past = now - dt.timedelta(hours=2)
    reminder = Reminder.objects.create(
        user=normal_user, title="Daily standup", remind_at=past, recurrence="daily"
    )
    assert reminder.is_due()

    response = client.post(f"{REMINDERS}{reminder.id}/complete/", {}, format="json")
    assert response.status_code == 200
    reminder.refresh_from_db()
    assert reminder.completed is False  # rescheduled, not finished
    assert reminder.remind_at > now


def test_one_time_complete_stays_completed(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    reminder = Reminder.objects.create(
        user=normal_user, title="One off", remind_at=timezone.now() + dt.timedelta(hours=1)
    )
    response = client.post(f"{REMINDERS}{reminder.id}/complete/", {}, format="json")
    reminder.refresh_from_db()
    assert response.status_code == 200
    assert reminder.completed is True


def test_custom_interval_recurrence(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        REMINDERS,
        {
            "title": "Water plants",
            "remind_at": "2026-08-20T09:00:00Z",
            "recurrence": "custom",
            "interval_days": 3,
        },
        format="json",
    )
    assert response.status_code == 201
    reminder = Reminder.objects.get(user=normal_user)
    assert reminder.interval_days == 3
    assert reminder.next_remind_at() - reminder.remind_at == dt.timedelta(days=3)


def test_dashboard_lists_upcoming(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    Reminder.objects.create(user=normal_user, title="Important task", remind_at=timezone.now() + dt.timedelta(hours=1))
    Reminder.objects.create(user=normal_user, title="Done task", remind_at=timezone.now() - dt.timedelta(hours=1))
    response = client.get("/api/v1/dashboard")
    titles = [r["title"] for r in response.data["reminders"]]
    assert "Important task" in titles
    assert "Done task" not in titles


def test_reminder_isolation(api, db, logged_in, normal_user):
    from apps.accounts.models import User

    other = User.objects.create_user(email="other3@example.com", password=PASSWORD)
    reminder = Reminder.objects.create(user=other, title="theirs", remind_at=timezone.now())
    client = logged_in(normal_user)
    assert client.get(f"{REMINDERS}{reminder.id}/").status_code == 404
    assert client.get(REMINDERS).data["count"] == 0