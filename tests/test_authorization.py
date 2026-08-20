"""Authorization tests: module access is enforced server-side, not just hidden."""

from __future__ import annotations

from tests.conftest import PASSWORD

BULLDROP_LIST = "/api/v1/bulldrop/accounts/"
INTERNLIK_LIST = "/api/v1/internlik/entries/"
ADMIN_USERS = "/api/v1/admin/users/"
DASHBOARD = "/api/v1/dashboard"


def _login(api, user):
    response = api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    csrf = api.cookies.get("myday_csrftoken")
    if csrf is not None:
        api.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


def test_normal_user_cannot_access_bulldrop(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    assert client.get(BULLDROP_LIST).status_code == 403


def test_normal_user_cannot_access_internlik(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    assert client.get(INTERNLIK_LIST).status_code == 403


def test_normal_user_cannot_access_admin(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    assert client.get(ADMIN_USERS).status_code == 403


def test_bulldrop_user_can_access_bulldrop(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    assert client.get(BULLDROP_LIST).status_code == 200


def test_bulldrop_user_cannot_access_internlik(api, db, logged_in, bulldrop_user):
    client = logged_in(bulldrop_user)
    assert client.get(INTERNLIK_LIST).status_code == 403


def test_internlik_user_cannot_access_bulldrop(api, db, logged_in, internlik_user):
    client = logged_in(internlik_user)
    assert client.get(BULLDROP_LIST).status_code == 403


def test_internlik_user_can_access_internlik(api, db, logged_in, internlik_user):
    client = logged_in(internlik_user)
    assert client.get(INTERNLIK_LIST).status_code == 200


def test_admin_can_access_everything(api, db, logged_in, admin_user):
    client = logged_in(admin_user)
    assert client.get(BULLDROP_LIST).status_code == 200
    assert client.get(INTERNLIK_LIST).status_code == 200
    assert client.get(ADMIN_USERS).status_code == 200


def test_unauth_requests_denied(api, db):
    assert api.get(BULLDROP_LIST).status_code == 401
    assert api.get(INTERNLIK_LIST).status_code == 401
    assert api.get(ADMIN_USERS).status_code == 401


def test_dashboard_hides_unpermitted_modules(api, db, logged_in, normal_user, bulldrop_user, internlik_user):
    client = logged_in(normal_user)
    response = client.get(DASHBOARD)
    assert response.status_code == 200
    assert "bulldrop" not in response.data
    assert "internlik" not in response.data
    assert "next_class" in response.data
    assert "reminders" in response.data

    client = logged_in(bulldrop_user)
    response = client.get(DASHBOARD)
    assert "bulldrop" in response.data
    assert "internlik" not in response.data

    client = logged_in(internlik_user)
    response = client.get(DASHBOARD)
    assert "bulldrop" not in response.data
    assert "internlik" in response.data


def test_dashboard_shows_all_for_admin(api, db, logged_in, admin_user):
    client = logged_in(admin_user)
    response = client.get(DASHBOARD)
    assert "bulldrop" in response.data
    assert "internlik" in response.data