"""BullDrop tests: permissions, claims, server-side timer, history, promos."""

from __future__ import annotations

import datetime as dt
from unittest import mock

from django.utils import timezone

from apps.bulldrop.models import BullDropAccount, BullDropClaim
from apps.core.models import AuditLog

from tests.conftest import PASSWORD

ACCOUNTS = "/api/v1/bulldrop/accounts/"
CLAIMS = "/api/v1/bulldrop/claims/"


def _create_account(user, name="Account #1", **kwargs):
    return BullDropAccount.objects.create(user=user, name=name, **kwargs)


def test_bulldrop_user_can_create_account(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    response = client.post(ACCOUNTS, {"name": "Main", "username": "gamer1", "notes": "primary"}, format="json")
    assert response.status_code == 201
    account = BullDropAccount.objects.get(user=bulldrop_user)
    assert account.name == "Main"
    assert account.username == "gamer1"


def test_normal_user_cannot_create_account(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(ACCOUNTS, {"name": "Main"}, format="json")
    assert response.status_code == 403


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

    # Claim it.
    response = client.post(
        f"{ACCOUNTS}{account.id}/claim/",
        {"promo_code": "ABC123", "note": "first claim"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "waiting"
    assert response.data["remaining_seconds"] > 0
    assert response.data["claim"]["promo_code"] == "ABC123"
    assert BullDropClaim.objects.filter(account=account, promo_code="ABC123").exists()


def test_claim_duplicate_rejected(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)
    client.post(f"{ACCOUNTS}{account.id}/claim/", {"promo_code": "ABC123"}, format="json")
    response = client.post(f"{ACCOUNTS}{account.id}/claim/", {"promo_code": "XYZ999"}, format="json")
    assert response.status_code == 409
    assert BullDropClaim.objects.count() == 1


def test_claim_rejects_other_users_account(api, db, logged_in, bulldrop_user, internlik_user):
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
    claim = account.last_claim

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


def test_claim_history_and_promo_search(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    a1 = _create_account(bulldrop_user, name="Account #1")
    a3 = _create_account(bulldrop_user, name="Account #3")

    now = timezone.now()
    BullDropClaim.objects.create(account=a1, promo_code="ABC123", claimed_at=now - dt.timedelta(hours=2))
    BullDropClaim.objects.create(account=a3, promo_code="X7K92", claimed_at=now - dt.timedelta(hours=1))

    response = client.get(CLAIMS)
    assert response.status_code == 200
    assert len(response.data["results"]) == 2

    # Search: which account used ABC123?
    response = client.get(f"{CLAIMS}?promo=ABC123")
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["account_name"] == "Account #1"
    assert results[0]["promo_code"] == "ABC123"


def test_summary_counts(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    a1 = _create_account(bulldrop_user)
    a2 = _create_account(bulldrop_user, name="A2")
    a3 = _create_account(bulldrop_user, name="A3")

    client.post(f"{ACCOUNTS}{a1.id}/claim/", {}, format="json")
    client.post(f"{ACCOUNTS}{a2.id}/claim/", {}, format="json")

    response = client.get(f"{CLAIMS}summary/")
    assert response.data == {"ready": 1, "waiting": 2}

    # Claims are audited.
    assert AuditLog.objects.filter(action="bulldrop.claimed").count() == 2


def test_claim_audit_logged(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    account = _create_account(bulldrop_user)
    client.post(f"{ACCOUNTS}{account.id}/claim/", {"promo_code": "P1"}, format="json")
    entry = AuditLog.objects.filter(action="bulldrop.claimed").first()
    assert entry.metadata == {"promo_code": "P1"}