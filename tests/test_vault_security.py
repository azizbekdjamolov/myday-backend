"""Vault security dashboard endpoint tests."""

from __future__ import annotations

from apps.core.encryption import encrypt
from apps.vault.models import VaultItem

SECURITY = "/api/v1/vault/items/security/"


def _item(user, title, password=""):
    return VaultItem.objects.create(
        user=user,
        category="accounts",
        title=title,
        encrypted_password=encrypt(password) if password else "",
    )


def test_security_requires_auth(api, db):
    assert api.get(SECURITY).status_code == 401


def test_security_buckets(api, db, logged_in, normal_user):
    _item(normal_user, "Strong", "K8#vL2!qP9@xZm")
    _item(normal_user, "Weak", "short1")
    _item(normal_user, "Reused A", "SamePassword99!")
    _item(normal_user, "Reused B", "SamePassword99!")
    _item(normal_user, "NoPassword")  # ignored — no stored password

    client = logged_in(normal_user)
    data = client.get(SECURITY).data
    assert data["total"] == 4
    assert data["weak"]["count"] == 1
    assert data["reused"]["count"] == 2
    assert data["strong"]["count"] == 1
    assert data["score"] == 25
    assert {i["title"] for i in data["weak"]["items"]} == {"Weak"}
    assert {i["title"] for i in data["reused"]["items"]} == {"Reused A", "Reused B"}


def test_security_never_exposes_passwords(api, db, logged_in, normal_user):
    import json

    secret = "K8#vL2!qP9@xZm"
    _item(normal_user, "Gmail", secret)
    client = logged_in(normal_user)
    body = json.dumps(client.get(SECURITY).data)
    assert secret not in body


def test_security_isolated_per_user(api, db, logged_in, normal_user, bulldrop_user):
    _item(bulldrop_user, "NotMine", "weakpw")
    client = logged_in(normal_user)
    assert client.get(SECURITY).data["total"] == 0
