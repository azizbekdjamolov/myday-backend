"""Internlik tests: permission gating and strict user isolation."""

from __future__ import annotations

from apps.internlik.models import InternlikEntry

from tests.conftest import PASSWORD

ENTRIES = "/api/v1/internlik/entries/"


def test_authorized_user_can_crud(api, db, logged_in, internlik_user):
    client = logged_in(internlik_user)
    response = client.post(ENTRIES, {"kind": "application", "title": "Internship app", "body": "details"}, format="json")
    assert response.status_code == 201

    entry_id = response.data["id"]
    response = client.get(f"{ENTRIES}{entry_id}/")
    assert response.status_code == 200
    assert response.data["title"] == "Internship app"

    response = client.patch(f"{ENTRIES}{entry_id}/", {"status": "interview"}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "interview"

    assert client.delete(f"{ENTRIES}{entry_id}/").status_code == 204


def test_unauthorized_user_denied(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.get(ENTRIES)
    assert response.status_code == 403


def test_bulldrop_user_denied_internlik(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    assert client.get(ENTRIES).status_code == 403


def test_user_cannot_see_others_entries(api, db, logged_in, internlik_user):
    entry = InternlikEntry.objects.create(
        user=internlik_user, kind="note", title="secret intern note", body="confidential"
    )

    from apps.accounts.models import User

    other = User.objects.create_user(email="intern2@example.com", password=PASSWORD)
    from apps.permissions.models import INTERNLIK_ACCESS
    from apps.permissions.services import grant_permission

    grant_permission(user=other, code=INTERNLIK_ACCESS)
    client = logged_in(other)

    assert client.get(f"{ENTRIES}{entry.id}/").status_code == 404
    assert client.patch(f"{ENTRIES}{entry.id}/", {"title": "hacked"}, format="json").status_code == 404
    assert client.delete(f"{ENTRIES}{entry.id}/").status_code == 404
    assert client.get(ENTRIES).data["count"] == 0


def test_admin_can_access_internlik(api, db, logged_in, admin_user):
    client = logged_in(admin_user)
    assert client.get(ENTRIES).status_code == 200