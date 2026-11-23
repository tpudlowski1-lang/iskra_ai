"""Persistent SQLite API credential registry.

Only SHA-256 digests of high-entropy bearer tokens are persisted. This is a
single-instance backend; use PostgreSQL before running multiple app instances.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time

from iskra.security.principal import Principal


@dataclass(frozen=True)
class IssuedCredential:
    credential_id: str
    token: str


class CredentialStoreUnavailable(RuntimeError):
    """Raised when the credential database cannot be safely accessed."""


class SQLiteCredentialStore:
    def __init__(self, database_path):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("Rejestr wymaga trwałej ścieżki pliku")
        self.database_path = os.path.abspath(database_path)
        parent = os.path.dirname(self.database_path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connection = sqlite3.connect(self.database_path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.Error as exc:
            raise CredentialStoreUnavailable("Credential database unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def _initialize(self):
        try:
            # Restrict the database file immediately after SQLite creates it.
            with self._connection() as connection:
                os.chmod(self.database_path, 0o600)
                with connection:
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
        except OSError as exc:
            raise CredentialStoreUnavailable("Credential database permissions could not be secured") from exc

    @staticmethod
    def _timestamp(value, field):
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Nieprawidłowy czas: {field}") from None
        if not math.isfinite(result):
            raise ValueError(f"Nieprawidłowy czas: {field}")
        return result

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(self, principal, expires_at=None):
        if not isinstance(principal, Principal):
            raise TypeError("Wymagany jest zweryfikowany Principal")
        expiry = self._timestamp(expires_at, "expires_at")
        now = time.time()
        if expiry is not None and expiry <= now:
            raise ValueError("Token musi wygasać w przyszłości")
        credential_id = secrets.token_urlsafe(18)
        token = secrets.token_urlsafe(48)
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
                    (credential_id, self._digest(token), principal.subject,
                     principal.tenant_id, roles_json, now, expiry),
                )
        return IssuedCredential(credential_id, token)

    def authenticate(self, token, now=None):
        if not isinstance(token, str) or not token or len(token) > 512:
            return None
        current = self._timestamp(now, "now")
        if current is None:
            current = time.time()
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
        if row["expires_at"] is not None and current >= row["expires_at"]:
            return None
        try:
            roles = frozenset(json.loads(row["roles_json"]))
            return Principal(row["subject"], row["tenant_id"], roles)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def revoke(self, credential_id):
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
