"""Environment configuration helpers.

All secrets and environment-dependent configuration are read from the
environment (via a ``.env`` file in development). Values are validated at
import time so misconfiguration fails fast.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def env_secret(key: str, default: str = "") -> str:
    """Read a secret from the environment, failing loudly when absent.

    ``default`` must be empty in production so a missing secret is an error
    rather than a silent security hole.
    """
    value = env_str(key, default)
    if not value:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return value


def env_base64_key(key: str, required: bool) -> bytes:
    """Read a base64-encoded binary key (e.g. the vault encryption key)."""
    raw = env_str(key, "")
    if not raw:
        if not required:
            return b""
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"Environment variable '{key}' must be valid base64.") from exc
    if len(decoded) < 32:
        raise RuntimeError(f"Environment variable '{key}' must decode to at least 32 bytes.")
    return decoded