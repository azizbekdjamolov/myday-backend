"""Development settings. Imported by default via config/settings/__init__.py."""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .env import env_bool

DEBUG = True

if env_bool("DJANGO_DEV_LOG_SQL", False):
    LOGGING["loggers"]["django.db.backends"] = {"level": "DEBUG"}  # noqa: F405