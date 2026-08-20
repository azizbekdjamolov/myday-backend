"""Production settings. Selected via DJANGO_SETTINGS_MODULE=config.settings.prod."""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .env import env_bool

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
JWT_AUTH_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# In production the JWT cookie must be SameSite=Lax + Secure. The refresh
# cookie should be scoped to the API host in a split-domain deployment.

DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405