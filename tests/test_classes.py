"""Class schedule tests: recurring, one-time, reminder timing."""

from __future__ import annotations

import datetime as dt
from unittest import mock

from django.utils import timezone

from apps.schedule.models import ClassSchedule

from tests.conftest import PASSWORD

CLASSES = "/api/v1/schedule/classes/"


def _login(api, user):
    response = api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    csrf = api.cookies.get("myday_csrftoken")
    if csrf is not None:
        api.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


def _now():
    return timezone.now()


def test_create_recurring_class(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        CLASSES,
        {
            "group_name": "Python-24",
            "days_of_week": [1, 3, 5],  # Tue, Thu, Sat
            "start_time": "18:00:00",
            "reminder_minutes": 60,
            "is_recurring": True,
        },
        format="json",
    )
    assert response.status_code == 201
    cls = ClassSchedule.objects.get(user=normal_user)
    assert cls.days_of_week == [1, 3, 5]
    assert cls.is_recurring


def test_create_one_time_class(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        CLASSES,
        {
            "group_name": "Exam",
            "days_of_week": [],
            "start_time": "09:00:00",
            "is_recurring": False,
            "specific_date": "2026-08-25",
        },
        format="json",
    )
    assert response.status_code == 201


def test_recurring_class_requires_days(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        CLASSES,
        {"group_name": "X", "days_of_week": [], "start_time": "10:00:00", "is_recurring": True},
        format="json",
    )
    assert response.status_code == 400


def test_one_time_class_requires_date(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        CLASSES,
        {"group_name": "X", "days_of_week": [], "start_time": "10:00:00", "is_recurring": False},
        format="json",
    )
    assert response.status_code == 400


def test_class_state_today_and_remaining(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    now = _now()
    # Class today at 18:00, reminder 60 min before.
    today_18 = now.replace(hour=18, minute=0, second=0, microsecond=0)
    cls = ClassSchedule.objects.create(
        user=normal_user,
        group_name="Python-24",
        days_of_week=[now.weekday()],
        start_time=dt.time(18, 0),
        reminder_minutes=60,
    )

    with mock.patch("django.utils.timezone.now", return_value=today_18 - dt.timedelta(hours=1, minutes=36)):
        detail = client.get(f"{CLASSES}{cls.id}/").data
        assert detail["status"] == "today"
        assert detail["remaining_seconds"] == 60 * 60 + 36 * 60  # 1h36m
        assert detail["reminder_minutes"] == 60

    with mock.patch("django.utils.timezone.now", return_value=today_18 + dt.timedelta(minutes=5)):
        detail = client.get(f"{CLASSES}{cls.id}/").data
        # Recurring classes never stay "completed" — the next week's instance shows.
        assert detail["status"] in ("upcoming", "today")
        assert detail["remaining_seconds"] > 0


def test_one_time_class_completes(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    past = (_now() - dt.timedelta(days=1)).date()
    cls = ClassSchedule.objects.create(
        user=normal_user,
        group_name="Old Exam",
        days_of_week=[],
        start_time=dt.time(10, 0),
        is_recurring=False,
        specific_date=past,
    )
    detail = client.get(f"{CLASSES}{cls.id}/").data
    assert detail["status"] == "completed"
    assert detail["next_at"] is None


def test_reminder_timing_before_class(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    now = _now()
    # Next class starts in 90 minutes, reminder set 60 min before.
    target = now + dt.timedelta(minutes=90)
    cls = ClassSchedule.objects.create(
        user=normal_user,
        group_name="Python-24",
        days_of_week=[target.weekday()],
        start_time=target.time(),
        reminder_minutes=60,
    )
    with mock.patch("django.utils.timezone.now", return_value=now):
        detail = client.get(f"{CLASSES}{cls.id}/").data
    reminder_at = dt.datetime.fromisoformat(detail["reminder_at"])
    assert reminder_at == target - dt.timedelta(minutes=60)


def test_class_isolation_between_users(api, db, logged_in, normal_user):
    from apps.accounts.models import User

    other = User.objects.create_user(email="other2@example.com", password=PASSWORD)
    cls = ClassSchedule.objects.create(
        user=other, group_name="Theirs", days_of_week=[0], start_time=dt.time(9, 0)
    )
    client = logged_in(normal_user)
    assert client.get(f"{CLASSES}{cls.id}/").status_code == 404
    assert client.get(CLASSES).data["count"] == 0


def test_dashboard_next_class(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    now = _now()
    target = now + dt.timedelta(hours=3)
    ClassSchedule.objects.create(
        user=normal_user,
        group_name="Python-24",
        days_of_week=[target.weekday()],
        start_time=target.time(),
        reminder_minutes=30,
    )
    with mock.patch("django.utils.timezone.now", return_value=now):
        response = client.get("/api/v1/dashboard")
    assert response.data["next_class"]["group_name"] == "Python-24"
    assert response.data["next_class"]["remaining_seconds"] > 0