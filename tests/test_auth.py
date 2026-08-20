"""Authentication tests: register, login, logout, refresh, password change."""

from __future__ import annotations

from apps.accounts.models import User

from tests.conftest import PASSWORD, login

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"


def test_register_creates_user(api, db):
    response = api.post(
        REGISTER,
        {"email": "New@Example.com", "name": "New", "password": PASSWORD, "password_confirm": PASSWORD},
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.filter(email__iexact="new@example.com").exists()
    user = User.objects.get(email__iexact="new@example.com")
    assert user.check_password(PASSWORD)
    # New users start with no module permissions.
    assert user.permission_codes() == set()


def test_register_password_mismatch(api, db):
    response = api.post(
        REGISTER,
        {"email": "x@example.com", "password": PASSWORD, "password_confirm": "Different123!"},
        format="json",
    )
    assert response.status_code == 400


def test_register_weak_password_rejected(api, db):
    response = api.post(
        REGISTER,
        {"email": "x@example.com", "password": "short", "password_confirm": "short"},
        format="json",
    )
    assert response.status_code == 400


def test_login_sets_cookies_and_returns_user(api, db, normal_user):
    response = api.post(LOGIN, {"email": normal_user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    assert "myday_access" in api.cookies
    assert "myday_refresh" in api.cookies
    assert response.data["email"] == normal_user.email


def test_login_wrong_password(api, db, normal_user):
    response = api.post(LOGIN, {"email": normal_user.email, "password": "WrongPass123!"}, format="json")
    assert response.status_code == 401


def test_login_deactivated_user(api, db, normal_user):
    normal_user.is_active = False
    normal_user.save()
    response = api.post(LOGIN, {"email": normal_user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 403


def test_me_requires_auth(api, db):
    assert api.get(ME).status_code == 401


def test_me_returns_permissions(api, db, logged_in, both_user):
    client = logged_in(both_user)
    response = client.get(ME)
    assert response.status_code == 200
    assert set(response.data["permissions"]) == {"BULLDROP_ACCESS", "INTERNLIK_ACCESS"}


def test_refresh_rotates_cookies(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    old_refresh = client.cookies["myday_refresh"].value
    response = client.post(REFRESH, {}, format="json")
    assert response.status_code == 200
    assert client.cookies["myday_refresh"].value != old_refresh


def test_refresh_without_csrf_rejected(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    client.defaults = {}  # drop the CSRF echo
    response = client.post(REFRESH, {}, format="json")
    assert response.status_code == 401


def test_logout_clears_cookies(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(LOGOUT, {}, format="json")
    assert response.status_code == 200
    assert client.get(ME).status_code == 401


def test_change_password(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        "/api/v1/auth/change-password",
        {"current_password": PASSWORD, "new_password": "NewPassword123!"},
        format="json",
    )
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.check_password("NewPassword123!")


def test_change_password_wrong_current(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        "/api/v1/auth/change-password",
        {"current_password": "WrongPass123!", "new_password": "NewPassword123!"},
        format="json",
    )
    assert response.status_code == 403


def test_password_reset_flow(api, db, normal_user):
    response = api.post("/api/v1/auth/password-reset/request", {"email": normal_user.email}, format="json")
    assert response.status_code == 200
    token = response.data.get("dev_token")
    assert token

    response = api.post(
        "/api/v1/auth/password-reset/confirm",
        {"token": token, "new_password": "ResetPassword123!"},
        format="json",
    )
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.check_password("ResetPassword123!")
    # Old password no longer works.
    assert api.post(LOGIN, {"email": normal_user.email, "password": PASSWORD}, format="json").status_code == 401


def test_password_reset_hides_existence(api, db):
    response = api.post("/api/v1/auth/password-reset/request", {"email": "ghost@example.com"}, format="json")
    assert response.status_code == 200
    assert "dev_token" not in response.data


def test_profile_update(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.patch("/api/v1/auth/profile", {"name": "New Name"}, format="json")
    assert response.status_code == 200
    normal_user.refresh_from_db()
    assert normal_user.name == "New Name"