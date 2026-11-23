"""Tenant-aware request rate limiting for the Flask application.

The default in-memory backend is suitable only for a single process. Multi-
instance deployments must configure a shared backend via RATELIMIT_STORAGE_URI.
"""
import os

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from iskra.security.principal import principal_from_environ


def rate_limit_key():
    """Use trusted tenant identity when available; otherwise use client IP."""
    principal = principal_from_environ(request.environ)
    if principal is not None:
        return f"tenant:{principal.tenant_id}"
    return get_remote_address()


def create_rate_limiter(app, environ=None, default_limits=None):
    """Attach a bounded default limiter, configurable for shared storage."""
    env = os.environ if environ is None else environ
    enabled = str(env.get("ISKRA_RATE_LIMIT_ENABLED", "true")).strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None
    if enabled not in {"1", "true", "yes", "on"}:
        raise ValueError("ISKRA_RATE_LIMIT_ENABLED musi być wartością logiczną")
    storage_uri = str(env.get("RATELIMIT_STORAGE_URI", "memory://")).strip()
    if not storage_uri:
        raise ValueError("RATELIMIT_STORAGE_URI nie może być puste")
    # Unit/integration test runs issue intentionally high-volume parallel requests.
    # Disable the application-wide default limiter only in an explicitly marked
    # test process; dedicated limiter tests use a separate Flask app without this flag.
    testing = str(env.get("ISKRA_TESTING", "")).strip().lower() in {"1", "true", "yes", "on"}
    if testing:
        app.config["RATELIMIT_ENABLED"] = False
    limits = default_limits if default_limits is not None else ["60 per minute"]
    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=limits,
        storage_uri=storage_uri,
        strategy="fixed-window",
        headers_enabled=True,
    )
    limiter.init_app(app)
    return limiter
