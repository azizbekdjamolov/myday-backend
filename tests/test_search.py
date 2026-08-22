"""Global search endpoint tests: permissions, ownership, scoping."""

from __future__ import annotations

from apps.bulldrop.models import BullDropAccount
from apps.internlik.models import InternlikEntry
from apps.reminders.models import Reminder
from apps.schedule.models import ClassSchedule
from apps.vault.models import VaultItem

from tests.conftest import PASSWORD

SEARCH = "/api/v1/search"


def _seed(user):
    ClassSchedule.objects.create(user=user, group_name="Python-24", days_of_week=[0], start_time="18:00")
    Reminder.objects.create(user=user, title="GitHub project", remind_at="2026-01-01T10:00:00Z")
    VaultItem.objects.create(user=user, category="accounts", title="Gmail")
    BullDropAccount.objects.create(user=user, name="Account #3", browser="chrome")
    InternlikEntry.objects.create(user=user, kind="application", title="Google internship")


def test_search_requires_auth(api, db):
    assert api.get(SEARCH, {"q": "py"}).status_code == 401


def test_search_returns_own_results(api, db, logged_in, both_user):
    _seed(both_user)
    client = logged_in(both_user)
    # both_user holds BULLDROP + INTERNLIK: every group is searchable.
    for query, expected_type in [
        ("pyth", "class"),
        ("gith", "reminder"),
        ("gma", "vault"),
        ("accou", "bulldrop"),
        ("goog", "internlik"),
    ]:
        response = client.get(SEARCH, {"q": query})
        assert response.status_code == 200
        types = {g["type"] for g in response.data["groups"]}
        assert expected_type in types, f"{query}: {types}"


def test_search_hides_modules_without_permission(api, db, logged_in, normal_user):
    _seed(normal_user)
    client = logged_in(normal_user)
    assert "vault" in {g["type"] for g in client.get(SEARCH, {"q": "gma"}).data["groups"]}
    assert "class" in {g["type"] for g in client.get(SEARCH, {"q": "pyth"}).data["groups"]}
    assert "reminder" in {g["type"] for g in client.get(SEARCH, {"q": "gith"}).data["groups"]}
    # No module permission: these must never appear.
    assert client.get(SEARCH, {"q": "accou"}).data["groups"] == []
    assert client.get(SEARCH, {"q": "goog"}).data["groups"] == []


def test_search_never_returns_other_users_data(api, db, logged_in, normal_user, bulldrop_user):
    _seed(bulldrop_user)  # belongs to another user entirely
    client = logged_in(normal_user)
    response = client.get(SEARCH, {"q": "on"})
    assert all(len(g["items"]) == 0 for g in response.data["groups"]) or response.data["groups"] == []


def test_search_short_query_noop(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.get(SEARCH, {"q": "p"})
    assert response.data["groups"] == []


def test_vault_search_titles_only(api, db, logged_in, normal_user):
    # The username is encrypted; searching for it must NOT hit via global search.
    VaultItem.objects.create(
        user=normal_user, category="accounts", title="Gmail", encrypted_username="secretuser@example.com"
    )
    client = logged_in(normal_user)
    response = client.get(SEARCH, {"q": "secretuser"})
    assert response.data["groups"] == []
    response = client.get(SEARCH, {"q": "gmail"})
    vault_groups = [g for g in response.data["groups"] if g["type"] == "vault"]
    assert len(vault_groups[0]["items"]) == 1

