"""BullDrop tests: permissions, ownership, browser field, server-side timer, filters."""

from __future__ import annotations

import datetime as dt
from unittest import mock

from django.utils import timezone

from apps.bulldrop.models import BullDropAccount, BullDropClaim
from apps.core.models import AuditLog

from tests.conftest import PASSWORD

ACCOUNTS = "/api/v1/bulldrop/accounts/"


def _create_account(user, name="Account #1", **kwargs):
    return BullDropAccount.objects.create(user=user, name=name, **kwargs)


def test_bulldrop_user_can_create_account(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    response = client.post(
        ACCOUNTS,
        {"name": "Main", "username": "gamer1", "browser": "opera", "notes": "primary"},
        format="json",
    )
    assert response.status_code == 201
    account = BullDropAccount.objects.get(user=bulldrop_user)
    assert account.name == "Main"
    assert account.username == "gamer1"
    assert account.browser == "opera"
    assert response.data["browser_display"] == "Opera"


def test_browser_defaults_to_chrome_and_validates_choices(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    response = client.post(ACCOUNTS, {"name": "NoBrowser"}, format="json")
    assert response.status_code == 201
    assert BullDropAccount.objects.get(name="NoBrowser").browser == "chrome"

    response = client.post(ACCOUNTS, {"name": "Bad", "browser": "netscape"}, format="json")
    assert response.status_code == 400


def test_normal_user_cannot_create_account(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(ACCOUNTS, {"name": "Main"}, format="json")
    assert response.status_code == 403


def test_anonymous_cannot_list_accounts(api, db):
    assert api.get(ACCOUNTS).status_code == 401


def test_user_cannot_touch_another_users_account(api, db, logged_in, bulldrop_user):
    other = _create_account(bulldrop_user, name="Mine")
    client = logged_in(bulldrop_user)
    response = client.get(f"{ACCOUNTS}{other.id + 1000}/")
    assert response.status_code == 404

    # A user with a different account cannot read/delete this one.
    from apps.accounts.models import User

    attacker = User.objects.create_user(email="attacker@example.com", password=PASSWORD)
    from apps.permissions.services import grant_permission
    from apps.permissions.models import BULLDROP_ACCESS

    grant_permission(user=attacker, code=BULLDROP_ACCESS)
    client2 = logged_in(attacker)
    assert client2.get(f"{ACCOUNTS}{other.id}/").status_code == 404
    assert client2.delete(f"{ACCOUNTS}{other.id}/").status_code == 404


def test_claim_flow_ready_to_claimed(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)

    # New account: READY, no countdown.
    detail = client.get(f"{ACCOUNTS}{account.id}/").data
    assert detail["status"] == "ready"
    assert detail["remaining_seconds"] == 0

    # One click claims it — no promo code or note is requested.
    response = client.post(f"{ACCOUNTS}{account.id}/claim/", {}, format="json")
    assert response.status_code == 201
    assert response.data["status"] == "waiting"
    assert response.data["remaining_seconds"] > 0
    assert "claimed_at" in response.data["claim"]
    assert BullDropClaim.objects.filter(account=account).exists()


def test_claim_duplicate_rejected(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)
    client.post(f"{ACCOUNTS}{account.id}/claim/", {}, format="json")
    response = client.post(f"{ACCOUNTS}{account.id}/claim/", {}, format="json")
    assert response.status_code == 409
    assert BullDropClaim.objects.count() == 1


def test_claim_rejects_other_users_account(api, db, logged_in, bulldrop_user):
    from apps.accounts.models import User
    from apps.permissions.models import BULLDROP_ACCESS
    from apps.permissions.services import grant_permission

    account = _create_account(bulldrop_user)
    attacker = User.objects.create_user(email="attacker2@example.com", password=PASSWORD)
    grant_permission(user=attacker, code=BULLDROP_ACCESS)
    client = logged_in(attacker)
    response = client.post(f"{ACCOUNTS}{account.id}/claim/", {}, format="json")
    assert response.status_code == 404


def test_timer_ready_after_cooldown(api, db, logged_in, bulldrop_user, settings):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)
    now = timezone.now()
    client.post(f"{ACCOUNTS}{account.id}/claim/", {}, format="json")

    account.refresh_from_db()

    # 23 hours later: still waiting.
    with mock.patch("django.utils.timezone.now", return_value=now + dt.timedelta(hours=23)):
        detail = client.get(f"{ACCOUNTS}{account.id}/").data
        assert detail["status"] == "waiting"
        assert detail["remaining_seconds"] > 0

    # 24 hours + 1s later: READY again, countdown gone.
    with mock.patch("django.utils.timezone.now", return_value=now + dt.timedelta(hours=24, seconds=1)):
        detail = client.get(f"{ACCOUNTS}{account.id}/").data
        assert detail["status"] == "ready"
        assert detail["remaining_seconds"] == 0


def test_search_and_filters(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    ready = _create_account(bulldrop_user, name="Account #1", browser="chrome")
    waiting = _create_account(bulldrop_user, name="Account #2", browser="opera")
    duck = _create_account(bulldrop_user, name="Backup", username="dd@gg", browser="duckduckgo")
    client.post(f"{ACCOUNTS}{waiting.id}/claim/", {}, format="json")

    # Search by name…
    results = client.get(ACCOUNTS, {"search": "#2"}).data["results"]
    assert [a["id"] for a in results] == [waiting.id]
    # …and by username.
    results = client.get(ACCOUNTS, {"search": "dd@gg"}).data["results"]
    assert [a["id"] for a in results] == [duck.id]

    # Browser filter.
    results = client.get(ACCOUNTS, {"browser": "duckduckgo"}).data["results"]
    assert [a["id"] for a in results] == [duck.id]

    # Status filter matches the model's server-computed status.
    results = client.get(ACCOUNTS, {"status": "ready"}).data["results"]
    assert sorted(a["id"] for a in results) == sorted([ready.id, duck.id])
    results = client.get(ACCOUNTS, {"status": "waiting"}).data["results"]
    assert [a["id"] for a in results] == [waiting.id]


def test_summary_counts(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    a1 = _create_account(bulldrop_user)
    a2 = _create_account(bulldrop_user, name="A2")
    a3 = _create_account(bulldrop_user, name="A3")

    client.post(f"{ACCOUNTS}{a1.id}/claim/", {}, format="json")
    client.post(f"{ACCOUNTS}{a2.id}/claim/", {}, format="json")

    response = client.get(f"{ACCOUNTS}summary/")
    assert response.data == {"total": 3, "ready": 1, "waiting": 2}

    # Claims are audited without promo metadata.
    assert AuditLog.objects.filter(action="bulldrop.claimed").count() == 2
    entry = AuditLog.objects.filter(action="bulldrop.claimed").first()
    assert not entry.metadata


def test_edit_and_delete_account(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)

    response = client.patch(
        f"{ACCOUNTS}{account.id}/", {"name": "Renamed", "browser": "brave"}, format="json"
    )
    assert response.status_code == 200
    account.refresh_from_db()
    assert account.name == "Renamed"
    assert account.browser == "brave"

    assert client.delete(f"{ACCOUNTS}{account.id}/").status_code == 204
    assert not BullDropAccount.objects.filter(id=account.id).exists()


def test_claims_endpoint_removed(api, db, logged_in, bulldrop_user):
    """The promo-code history API no longer exists."""
    client = logged_in(bulldrop_user)
    assert client.get("/api/v1/bulldrop/claims/").status_code == 404
