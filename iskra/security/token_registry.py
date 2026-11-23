"""Hashed API credential registry with server-owned principal mapping.

The registry contains SHA-256 digests, never bearer secrets. Provision credentials
out of band and deliver raw tokens only once through a secret manager.
"""
import hashlib
import hmac
import json
import re

from iskra.security.principal import Principal


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TokenRegistry:
    """Immutable lookup of token digests to trusted request principals."""

    def __init__(self, entries):
        if not isinstance(entries, dict):
            raise ValueError("API_TOKEN_REGISTRY musi być obiektem JSON")
        parsed = {}
        for digest, definition in entries.items():
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                raise ValueError("Każdy klucz rejestru musi być skrótem SHA-256")
            if not isinstance(definition, dict):
                raise ValueError("Definicja tokenu musi być obiektem")
            if set(definition) != {"subject", "tenant_id", "roles"}:
                raise ValueError("Definicja tokenu wymaga subject, tenant_id i roles")
            roles = definition["roles"]
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise ValueError("roles musi być listą tekstowych ról")
            parsed[digest] = Principal(
                subject=definition["subject"],
                tenant_id=definition["tenant_id"],
                roles=frozenset(roles),
            )
        self._entries = parsed

    @staticmethod
    def digest(token):
        """Return the lowercase SHA-256 digest for provisioning a bearer token."""
        if not isinstance(token, str) or not token:
            raise ValueError("Token musi być niepustym tekstem")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, raw):
        try:
            entries = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise ValueError("API_TOKEN_REGISTRY zawiera nieprawidłowy JSON") from None
        return cls(entries)

    def authenticate(self, token):
        """Resolve a raw bearer token without storing or returning the secret."""
        if not isinstance(token, str) or not token:
            return None
        candidate = self.digest(token)
        matched = None
        # Compare every configured digest to avoid an early-exit timing signal.
        for digest, principal in self._entries.items():
            if hmac.compare_digest(candidate, digest):
                matched = principal
        return matched
