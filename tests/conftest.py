"""Pytest configuration and shared fixtures.

Uses a temporary SQLite database so tests never touch the real database.
Provides users with every permission combination and JWT-cookie API clients.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.permissions.models import BULLDROP_ACCESS, INTERNLIK_ACCESS
from apps.permissions.services import grant_permission

PASSWORD = "TestPass123!"

pytest_plugins = []


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _fast_throttles(settings):
    """Bump throttle rates so the suite never hits rate limits."""
    rates = dict(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
    for scope in rates:
        rates[scope] = "10000/min"
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = rates


@pytest.fixture(autouse=True)
def _short_vault_ttl(settings):
    settings.VAULT_AUTOLOCK_MINUTES = 60
    settings.VAULT_REVEAL_TTL_SECONDS = 30


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@pytest.fixture
def normal_user(db):
    return User.objects.create_user(email="normal@example.com", password=PASSWORD, name="Normal")


@pytest.fixture
def bulldrop_user(db):
    user = User.objects.create_user(email="bulldrop@example.com", password=PASSWORD, name="Bulldrop")
    grant_permission(user=user, code=BULLDROP_ACCESS)
    return user


@pytest.fixture
def internlik_user(db):
    user = User.objects.create_user(email="intern@example.com", password=PASSWORD, name="Intern")
    grant_permission(user=user, code=INTERNLIK_ACCESS)
    return user


@pytest.fixture
def both_user(db):
    user = User.objects.create_user(email="both@example.com", password=PASSWORD, name="Both")
    grant_permission(user=user, code=BULLDROP_ACCESS)
    grant_permission(user=user, code=INTERNLIK_ACCESS)
    return user


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
    grant_permission(user=user, code="ADMIN_ACCESS")
    return user


@pytest.fixture
def api():
    return APIClient()


def login(client: APIClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.content
    # The CSRF cookie is set on the login response; echo it back on writes.
    client.defaults = {}
    csrf = client.cookies.get("myday_csrftoken")
    if csrf is not None:
        client.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


@pytest.fixture
def logged_in(api):
    """Client authenticated as a given user via JWT cookies."""

    def _logged_in(user):
        login(api, user.email)
        return api

    return _logged_in