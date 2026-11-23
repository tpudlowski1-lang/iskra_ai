"""Hashed API credential registry; identities are never read from request data."""
import hashlib
import hmac
import json
import re

from iskra.security.principal import Principal


class CredentialConfigError(ValueError):
    """Raised when server-side credential configuration is malformed."""


def load_api_credentials(raw):
    """Load server-managed credentials keyed by SHA-256 token digests.

    Expected JSON: [{"token_sha256": "<64 lowercase hex>", "subject": "...",
    "tenant_id": "...", "roles": ["member"]}]. Raw API tokens are never stored.
    """
    if not raw:
        return {}

    try:
        records = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CredentialConfigError("ISKRA_API_CREDENTIALS_JSON is not valid JSON") from exc

    if not isinstance(records, list):
        raise CredentialConfigError("Credential configuration must be a JSON array")

    credentials = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise CredentialConfigError(f"Credential entry {index} must be an object")
        digest = record.get("token_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CredentialConfigError(f"Credential entry {index} has an invalid token_sha256")
        if digest in credentials:
            raise CredentialConfigError("Duplicate token_sha256 in credential configuration")
        try:
            credentials[digest] = Principal(
                subject=record.get("subject"),
                tenant_id=record.get("tenant_id"),
                roles=frozenset(record.get("roles", [])),
            )
        except (TypeError, ValueError) as exc:
            raise CredentialConfigError(f"Credential entry {index} has an invalid principal") from exc

    return credentials


def principal_for_token(token, credentials):
    """Resolve a token to a principal using constant-time digest comparisons."""
    if not isinstance(token, str) or not token or len(token) > 512:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for expected_digest, principal in credentials.items():
        if hmac.compare_digest(digest, expected_digest):
            return principal
    return None
