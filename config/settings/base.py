"""Base Django settings shared across environments.

Environment-specific settings live in :mod:`config.settings.dev` and
:mod:`config.settings.prod`. Secrets never live in this file.
"""

from __future__ import annotations

import json
from datetime import timedelta

import dj_database_url
from pythonjsonlogger.json import JsonFormatter

from .env import BASE_DIR, env_base64_key, env_bool, env_int, env_secret, env_str

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env_secret("DJANGO_SECRET_KEY")
DEBUG = False

ALLOWED_HOSTS = [h for h in env_str("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [
    o for o in env_str("CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",") if o
]
INTERNAL_IPS = env_str("INTERNAL_IPS", "127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "timezone_field",
    # Local apps
    "apps.accounts",
    "apps.core",
    "apps.permissions",
    "apps.vault",
    "apps.bulldrop",
    "apps.internlik",
    "apps.schedule",
    "apps.reminders",
    "apps.adminpanel",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600,
    )
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login"
PASSWORD_RESET_TIMEOUT = 3600

# JWT session cookies (HttpOnly, SameSite). Access token stays in memory on
# the client (never persisted), refresh token in an HttpOnly cookie.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("ACCESS_TOKEN_LIFETIME_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("REFRESH_TOKEN_LIFETIME_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ALGORITHM": "HS256",
}

# Cookies for JWT auth. Secure in production, HttpOnly always.
JWT_AUTH_COOKIE = "myday_access"
JWT_AUTH_REFRESH_COOKIE = "myday_refresh"
JWT_AUTH_COOKIE_SECURE = env_bool("JWT_AUTH_COOKIE_SECURE", False)
JWT_AUTH_COOKIE_HTTPONLY = True
JWT_AUTH_COOKIE_SAMESITE = "Lax"
JWT_AUTH_COOKIE_PATH = "/"

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.auth.JWTCookieAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "auth": "20/min",
        "bulldrop_claim": "10/m",
        "vault_reveal": "10/min",
    },
}

# CORS (dev only; prod uses same-origin)
CORS_ALLOWED_ORIGINS = env_str("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

# ---------------------------------------------------------------------------
# Cache / throttling backend
# ---------------------------------------------------------------------------
CACHE_URL = env_str("CACHE_URL", "")
if CACHE_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": CACHE_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "myday"}}

# ---------------------------------------------------------------------------
# Logging: structured JSON. Sensitive values are redacted by a filter.
# ---------------------------------------------------------------------------
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact": {"()": "apps.core.logging.RedactionFilter"},
        "request_id": {"()": "apps.core.logging.RequestIdFilter"},
    },
    "formatters": {
        "json": {
            "()": JsonFormatter,
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        },
        "plain": {"format": "%(asctime)s [%(levelname)s] %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact", "request_id"],
            "formatter": "json" if env_bool("JSON_LOGS", False) else "plain",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Vault encryption
# ---------------------------------------------------------------------------
REQUIRE_VAULT_MASTER_KEY = env_bool("REQUIRE_VAULT_MASTER_KEY", False)
VAULT_MASTER_KEY = env_base64_key("VAULT_MASTER_KEY", required=REQUIRE_VAULT_MASTER_KEY)
VAULT_FILE_MAX_SIZE = env_int("VAULT_FILE_MAX_SIZE", 5 * 1024 * 1024)
VAULT_REVEAL_TTL_SECONDS = env_int("VAULT_REVEAL_TTL_SECONDS", 30)
VAULT_AUTOLOCK_MINUTES = env_int("VAULT_AUTOLOCK_MINUTES", 5)

# Private file storage root (outside web root / MEDIA_ROOT)
PRIVATE_MEDIA_ROOT = env_str("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_storage"))

# ---------------------------------------------------------------------------
# BullDrop configuration
# ---------------------------------------------------------------------------
BULLDROP_COOLDOWN_SECONDS = env_int("BULLDROP_COOLDOWN_SECONDS", 86400)

# ---------------------------------------------------------------------------
# Timezone defaults
# ---------------------------------------------------------------------------
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = True
LANGUAGE_CODE = "en-us"

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = JWT_AUTH_COOKIE_SECURE
CSRF_COOKIE_HTTPONLY = False  # readable by JS so the SPA can echo it back
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "myday_csrftoken"

# Static files (Whitenoise)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

APPEND_SLASH = False

# App version used in operational logging.
APP_VERSION = env_str("APP_VERSION", "dev")

# A health-check safe list of sensitive header/field names that logging must
# never record.
SENSITIVE_LOG_FIELDS = json.loads(
    env_str(
        "SENSITIVE_LOG_FIELDS",
        '["password", "secret", "token", "authorization", "cookie", "api_key", "refresh", "access"]',
    )
)