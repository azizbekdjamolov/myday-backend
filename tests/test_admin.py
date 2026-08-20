"""Admin panel tests: permission grants/revokes, activate/deactivate."""

from __future__ import annotations

from apps.accounts.models import User
from apps.core.models import AuditLog

from tests.conftest import PASSWORD

USERS = "/api/v1/admin/users/"


def _login(api, user):
    response = api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    csrf = api.cookies.get("myday_csrftoken")
    if csrf is not None:
        api.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


def test_admin_lists_users(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    response = client.get(USERS)
    assert response.status_code == 200
    emails = [u["email"] for u in response.data["results"]]
    assert normal_user.email in emails


def test_admin_list_has_no_sensitive_data(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    response = client.get(USERS)
    user_payload = next(u for u in response.data["results"] if u["email"] == normal_user.email)
    assert "password" not in user_payload
    assert "vault" not in user_payload


def test_grant_and_revoke_bulldrop(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    response = client.post(
        f"{USERS}{normal_user.id}/permission/",
        {"permission": "BULLDROP_ACCESS", "action": "grant"},
        format="json",
    )
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.has_bulldrop_access
    assert AuditLog.objects.filter(action="permission.granted", resource_id=normal_user.id).exists()

    response = client.post(
        f"{USERS}{normal_user.id}/permission/",
        {"permission": "BULLDROP_ACCESS", "action": "revoke"},
        format="json",
    )
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert not normal_user.has_bulldrop_access


def test_grant_and_revoke_internlik(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    client.post(f"{USERS}{normal_user.id}/permission/", {"permission": "INTERNLIK_ACCESS", "action": "grant"}, format="json")
    normal_user.refresh_from_db()
    assert normal_user.has_internlik_access

    client.post(f"{USERS}{normal_user.id}/permission/", {"permission": "INTERNLIK_ACCESS", "action": "revoke"}, format="json")
    normal_user.refresh_from_db()
    assert not normal_user.has_internlik_access


def test_permission_change_applies_immediately(api, db, logged_in, admin_user, normal_user):
    """Granted access works on the very next request without re-login."""
    admin_client = logged_in(admin_user)
    admin_client.post(f"{USERS}{normal_user.id}/permission/", {"permission": "BULLDROP_ACCESS", "action": "grant"}, format="json")

    user_client = logged_in(normal_user)
    assert user_client.get("/api/v1/bulldrop/accounts/").status_code == 200


def test_deactivate_blocks_login(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    response = client.post(f"{USERS}{normal_user.id}/deactivate/", {}, format="json")
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.is_active is False

    # The deactivated user can no longer sign in.
    response = client.post("/api/v1/auth/login", {"email": normal_user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 403


def test_activate_restores_login(api, db, logged_in, admin_user, normal_user):
    client = logged_in(admin_user)
    client.post(f"{USERS}{normal_user.id}/deactivate/", {}, format="json")
    client.post(f"{USERS}{normal_user.id}/activate/", {}, format="json")
    normal_user.refresh_from_db()
    assert normal_user.is_active is True
    assert client.post("/api/v1/auth/login", {"email": normal_user.email, "password": PASSWORD}, format="json").status_code == 200


def test_admin_cannot_change_own_permissions(api, db, logged_in, admin_user):
    client = logged_in(admin_user)
    response = client.post(
        f"{USERS}{admin_user.id}/permission/",
        {"permission": "BULLDROP_ACCESS", "action": "revoke"},
        format="json",
    )
    assert response.status_code == 400


def test_admin_cannot_deactivate_self(api, db, logged_in, admin_user):
    client = logged_in(admin_user)
    response = client.post(f"{USERS}{admin_user.id}/deactivate/", {}, format="json")
    assert response.status_code == 400


def test_non_admin_cannot_manage_permissions(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        f"{USERS}{normal_user.id}/permission/",
        {"permission": "BULLDROP_ACCESS", "action": "grant"},
        format="json",
    )
    assert response.status_code == 403