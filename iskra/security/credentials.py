"""Persistent, tenant-bound API credential registry (SQLite prototype).

The registry stores only SHA-256 digests of high-entropy random bearer tokens.
It is consumed by WSGI authentication when CREDENTIAL_DB_PATH is configured.
The SQLite implementation remains a single-instance prototype.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Protocol

from iskra.security.principal import Principal


@dataclass(frozen=True)
class IssuedCredential:
    """A newly issued token; plaintext is returned once and never persisted."""

    credential_id: str
    token: str


class CredentialStore(Protocol):
    """Persistence contract for credential issuance, lookup, and revocation."""

    def issue(self, principal: Principal, expires_at: float | None = None) -> IssuedCredential:
        ...

    def authenticate(self, token: str, now: float | None = None) -> Principal | None:
        ...

    def revoke(self, credential_id: str) -> bool:
        ...


class SQLiteCredentialStore:
    """Single-instance credential registry; PostgreSQL is required for HA."""

    def __init__(self, database_path: str):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("Rejestr poświadczeń wymaga trwałej ścieżki pliku")
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        self._initialize()
        os.chmod(self.database_path, 0o600)

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_credentials (
                    credential_id TEXT PRIMARY KEY,
                    token_digest TEXT NOT NULL UNIQUE,
                    subject TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    revoked_at REAL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_credentials_subject "
                "ON api_credentials(subject, tenant_id)"
            )

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_time(value, field):
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Nieprawidłowy czas: {field}") from None
        if not math.isfinite(result):
            raise ValueError(f"Nieprawidłowy czas: {field}")
        return result

    def issue(self, principal: Principal, expires_at: float | None = None) -> IssuedCredential:
        if not isinstance(principal, Principal):
            raise TypeError("Wymagany jest zweryfikowany Principal")
        expiry = self._validate_time(expires_at, "expires_at")
        now = time.time()
        if expiry is not None and expiry <= now:
            raise ValueError("Token musi mieć datę ważności w przyszłości")

        credential_id = secrets.token_urlsafe(12)
        token = secrets.token_urlsafe(32)
        roles_json = json.dumps(sorted(principal.roles), separators=(",", ":"))
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO api_credentials
                    (credential_id, token_digest, subject, tenant_id, roles_json,
                     created_at, expires_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        credential_id,
                        self._digest(token),
                        principal.subject,
                        principal.tenant_id,
                        roles_json,
                        now,
                        expiry,
                    ),
                )
        return IssuedCredential(credential_id=credential_id, token=token)

    def authenticate(self, token: str, now: float | None = None) -> Principal | None:
        if not isinstance(token, str) or not token or len(token) > 512:
            return None
        current_time = self._validate_time(now, "now")
        if current_time is None:
            current_time = time.time()
        digest = self._digest(token)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT token_digest, subject, tenant_id, roles_json, expires_at, revoked_at
                FROM api_credentials WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        if not secrets.compare_digest(row["token_digest"], digest):
            return None
        if row["expires_at"] is not None and current_time >= row["expires_at"]:
            return None
        try:
            roles = frozenset(json.loads(row["roles_json"]))
            return Principal(
                subject=row["subject"],
                tenant_id=row["tenant_id"],
                roles=roles,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            # Corrupt or tampered registry records fail closed.
            return None

    def revoke(self, credential_id: str) -> bool:
        if not isinstance(credential_id, str) or not credential_id:
            return False
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE api_credentials SET revoked_at = ?
                    WHERE credential_id = ? AND revoked_at IS NULL
                    """,
                    (time.time(), credential_id),
                )
        return cursor.rowcount == 1
