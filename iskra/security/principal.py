"""Immutable, server-derived identity attached to authenticated requests."""
from dataclasses import dataclass


PRINCIPAL_ENV_KEY = "iskra.auth.principal"
PRINCIPAL_CREDENTIAL_ID_ENV_KEY = "iskra.auth.credential_id"
BROWSER_SESSION_TOKEN_ENV_KEY = "iskra.auth.browser_session_token"
BROWSER_SESSION_CSRF_DIGEST_ENV_KEY = "iskra.auth.browser_session_csrf_digest"
BROWSER_SESSION_COOKIE_NAME = "__Host-iskra_session"
ALLOWED_ROLES = frozenset({"admin", "member"})


@dataclass(frozen=True)
class Principal:
    """Authenticated subject and tenant scope; never construct from request data."""

    subject: str
    tenant_id: str
    roles: frozenset[str]

    def __post_init__(self):
        for field_name, value in (("subject", self.subject), ("tenant_id", self.tenant_id)):
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError(f"Nieprawidłowe pole principal: {field_name}")
        normalized = frozenset(self.roles)
        if not normalized or not normalized.issubset(ALLOWED_ROLES):
            raise ValueError("Principal musi mieć co najmniej jedną dozwoloną rolę")
        object.__setattr__(self, "roles", normalized)


SYSTEM_ADMIN = Principal(
    subject="api-token-admin",
    tenant_id="system",
    roles=frozenset({"admin"}),
)


def principal_from_environ(environ):
    """Return only the principal installed by trusted authentication middleware."""
    principal = environ.get(PRINCIPAL_ENV_KEY)
    return principal if isinstance(principal, Principal) else None
