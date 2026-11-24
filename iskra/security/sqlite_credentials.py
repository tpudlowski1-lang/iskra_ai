"""Persistent SQLite API credential registry with atomic lifecycle audit.

Only SHA-256 digests of high-entropy bearer tokens are persisted. This is a
single-instance backend; use PostgreSQL before running multiple app instances.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import stat
import time

from iskra.security.principal import ALLOWED_ROLES, Principal


@dataclass(frozen=True)
class IssuedCredential:
    credential_id: str
    token: str
    expires_at: float | None = None


@dataclass(frozen=True)
class BrowserSession:
    principal: Principal
    credential_id: str
    csrf_digest: str
    csrf_token: str | None
    expires_at: float


class CredentialStoreUnavailable(RuntimeError):
    """Raised when the credential database cannot be safely accessed."""


class LastTenantAdminError(ValueError):
    """Raised when an operation would leave a tenant without an active admin."""


class SQLiteCredentialStore:
    TENANT_DEFAULT_CREDENTIAL_TTL_SECONDS = 90 * 24 * 60 * 60
    TENANT_MAX_CREDENTIAL_TTL_SECONDS = 365 * 24 * 60 * 60

    def __init__(self, database_path, csrf_secret=None):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("Rejestr wymaga trwałej ścieżki pliku")
        self.database_path = os.path.abspath(database_path)
        configured_secret = csrf_secret if csrf_secret is not None else os.environ.get("ISKRA_CSRF_HMAC_SECRET", "")
        self.csrf_secret = configured_secret.encode("utf-8") if isinstance(configured_secret, str) else b""
        if self.csrf_secret and len(self.csrf_secret) < 32:
            raise ValueError("ISKRA_CSRF_HMAC_SECRET musi mieć co najmniej 32 bajty")
        parent = os.path.dirname(self.database_path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        self._initialize()

    @staticmethod
    def _effective_uid():
        return os.geteuid() if hasattr(os, "geteuid") else os.stat(".").st_uid

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
        """Initialize the registry only inside an owner-private directory.

        SQLite opens the database by path, so the containing directory must be
        inaccessible to other users. O_NOFOLLOW and descriptor checks reject
        symlinks, special files and files owned by another user before SQLite
        is allowed to open the path.
        """
        parent = os.path.dirname(self.database_path)
        filename = os.path.basename(self.database_path)
        directory_fd = None
        database_fd = None
        try:
            nofollow = getattr(os, "O_NOFOLLOW", None)
            directory_flag = getattr(os, "O_DIRECTORY", None)
            if nofollow is None or directory_flag is None:
                raise OSError("Platform must support O_NOFOLLOW and O_DIRECTORY")

            directory_fd = os.open(
                parent,
                os.O_RDONLY | directory_flag | nofollow,
            )
            directory_stat = os.fstat(directory_fd)
            if (not stat.S_ISDIR(directory_stat.st_mode)
                    or directory_stat.st_uid != self._effective_uid()
                    or directory_stat.st_mode & 0o077):
                raise OSError("Credential directory must be owned by the service user and mode 0700")

            try:
                database_fd = os.open(
                    filename,
                    os.O_CREAT | os.O_EXCL | os.O_RDWR | nofollow,
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                database_fd = os.open(
                    filename,
                    os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | nofollow,
                    dir_fd=directory_fd,
                )

            database_stat = os.fstat(database_fd)
            if (not stat.S_ISREG(database_stat.st_mode)
                    or database_stat.st_uid != self._effective_uid()
                    or database_stat.st_nlink != 1):
                raise OSError("Credential database must be a private regular file owned by the service user")
            os.fchmod(database_fd, 0o600)
        except OSError as exc:
            raise CredentialStoreUnavailable(
                "Credential database path or permissions could not be secured"
            ) from exc
        finally:
            if database_fd is not None:
                os.close(database_fd)
            if directory_fd is not None:
                os.close(directory_fd)

        try:
            with self._connection() as connection:
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
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS browser_sessions (
                            session_digest TEXT PRIMARY KEY,
                            credential_id TEXT NOT NULL,
                            csrf_digest TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            expires_at REAL NOT NULL,
                            revoked_at REAL,
                            FOREIGN KEY (credential_id) REFERENCES api_credentials(credential_id)
                        )
                        """
                    )
                    session_columns = {
                        row["name"] for row in connection.execute("PRAGMA table_info(browser_sessions)")
                    }
                    if "csrf_token" in session_columns:
                        # Existing sessions depended on a plaintext token. Invalidate
                        # them before removing that column; never migrate raw CSRF data.
                        connection.execute("DELETE FROM browser_sessions")
                        connection.execute("ALTER TABLE browser_sessions DROP COLUMN csrf_token")
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS idx_browser_sessions_credential "
                        "ON browser_sessions(credential_id, expires_at)"
                    )
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS credential_audit_events (
                            event_id TEXT PRIMARY KEY,
                            event_type TEXT NOT NULL CHECK (
                                event_type IN ('credential_issued', 'credential_revoked', 'credential_rotated')
                            ),
                            credential_id TEXT NOT NULL,
                            related_credential_id TEXT,
                            subject TEXT NOT NULL,
                            tenant_id TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            occurred_at REAL NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS idx_credential_audit_time "
                        "ON credential_audit_events(occurred_at DESC)"
                    )
        except sqlite3.Error as exc:
            raise CredentialStoreUnavailable("Credential database unavailable") from exc

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
    def _validate_actor(actor):
        if (not isinstance(actor, str) or not actor.strip()
                or len(actor) > 255 or any(ord(char) < 32 for char in actor)):
            raise ValueError("Nieprawidłowy identyfikator operatora")
        return actor.strip()

    @classmethod
    def _tenant_expiry(cls, expires_at, now):
        if expires_at is None:
            return now + cls.TENANT_DEFAULT_CREDENTIAL_TTL_SECONDS
        expiry = cls._timestamp(expires_at, "expires_at")
        if expiry is None or expiry <= now:
            raise ValueError("Token musi wygasać w przyszłości")
        if expiry > now + cls.TENANT_MAX_CREDENTIAL_TTL_SECONDS:
            raise ValueError("Tenant token nie może być ważny dłużej niż 365 dni")
        return expiry

    @staticmethod
    def _require_tenant_admin(principal):
        if (not isinstance(principal, Principal)
                or "admin" not in principal.roles
                or principal.tenant_id == "system"):
            raise PermissionError("Wymagany administrator tenant")

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue_browser_csrf_token(self, session_token):
        """Derive a stable CSRF token without persisting its plaintext value."""
        if not self.csrf_secret or not isinstance(session_token, str) or len(session_token) < 32:
            raise CredentialStoreUnavailable("Browser CSRF signing is not configured")
        return hmac.new(self.csrf_secret, session_token.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _record_event(connection, event_type, credential_id, principal, actor,
                      occurred_at, related_credential_id=None):
        connection.execute(
            """
            INSERT INTO credential_audit_events
                (event_id, event_type, credential_id, related_credential_id,
                 subject, tenant_id, actor, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                secrets.token_urlsafe(18),
                event_type,
                credential_id,
                related_credential_id,
                principal.subject,
                principal.tenant_id,
                actor,
                occurred_at,
            ),
        )

    def issue(self, principal, expires_at=None, actor="local-operator"):
        if not isinstance(principal, Principal):
            raise TypeError("Wymagany jest zweryfikowany Principal")
        if principal.tenant_id == "system":
            raise ValueError("Rejestr tenantów nie może wydawać poświadczeń dla tenant system")
        expiry = self._timestamp(expires_at, "expires_at")
        now = time.time()
        if expiry is not None and expiry <= now:
            raise ValueError("Token musi wygasać w przyszłości")
        actor = self._validate_actor(actor)
        credential_id = "cred_" + secrets.token_urlsafe(18)
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
                self._record_event(
                    connection, "credential_issued", credential_id,
                    principal, actor, now,
                )
        return IssuedCredential(credential_id, token, expiry)

    def authenticate_with_metadata(self, token, now=None):
        """Return the verified Principal and persistent credential ID."""
        if not isinstance(token, str) or not token or len(token) > 512:
            return None
        current = self._timestamp(now, "now")
        if current is None:
            current = time.time()
        digest = self._digest(token)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT credential_id, subject, tenant_id, roles_json, expires_at, revoked_at
                FROM api_credentials WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
        if row is None or row["tenant_id"] == "system" or row["revoked_at"] is not None:
            return None
        if row["expires_at"] is not None and current >= row["expires_at"]:
            return None
        try:
            roles = frozenset(json.loads(row["roles_json"]))
            principal = Principal(row["subject"], row["tenant_id"], roles)
            return principal, row["credential_id"]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def authenticate(self, token, now=None):
        authenticated = self.authenticate_with_metadata(token, now=now)
        return authenticated[0] if authenticated is not None else None

    def create_browser_session(self, principal, credential_id, session_token,
                               csrf_token, expires_at):
        """Create an opaque browser session tied to one active API credential."""
        if not isinstance(principal, Principal) or principal.tenant_id == "system":
            raise PermissionError("Browser sessions require a tenant Principal")
        if (not isinstance(credential_id, str) or not credential_id
                or not isinstance(session_token, str) or len(session_token) < 32
                or not isinstance(csrf_token, str) or len(csrf_token) < 32):
            raise ValueError("Invalid browser session material")
        expected_csrf = self.issue_browser_csrf_token(session_token)
        if not hmac.compare_digest(csrf_token, expected_csrf):
            raise ValueError("Invalid browser CSRF token")
        now = time.time()
        expiry = self._timestamp(expires_at, "expires_at")
        if expiry is None or expiry <= now or expiry > now + 8 * 60 * 60:
            raise ValueError("Browser session expiry must be within eight hours")
        with self._connection() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM browser_sessions WHERE expires_at <= ? OR (revoked_at IS NOT NULL AND revoked_at <= ?)",
                    (now, now - 30 * 24 * 60 * 60),
                )
                credential = connection.execute(
                    """
                    SELECT subject, tenant_id, roles_json, expires_at, revoked_at
                    FROM api_credentials WHERE credential_id = ?
                    """,
                    (credential_id,),
                ).fetchone()
                if (credential is None or credential["revoked_at"] is not None
                        or (credential["expires_at"] is not None and credential["expires_at"] <= now)):
                    raise PermissionError("Credential is no longer active")
                try:
                    stored_principal = Principal(
                        credential["subject"], credential["tenant_id"],
                        frozenset(json.loads(credential["roles_json"])),
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    raise CredentialStoreUnavailable("Credential metadata is invalid") from None
                if stored_principal != principal:
                    raise PermissionError("Credential Principal mismatch")
                if credential["expires_at"] is not None:
                    expiry = min(expiry, credential["expires_at"])
                connection.execute(
                    """
                    INSERT INTO browser_sessions
                    (session_digest, credential_id, csrf_digest,
                     created_at, expires_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (self._digest(session_token), credential_id,
                     self._digest(csrf_token), now, expiry),
                )
        return expiry

    def authenticate_browser_session(self, session_token, now=None):
        if not isinstance(session_token, str) or not session_token or len(session_token) > 512:
            return None
        current = self._timestamp(now, "now")
        if current is None:
            current = time.time()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT s.credential_id, s.csrf_digest, s.expires_at AS session_expires_at,
                       s.revoked_at AS session_revoked_at,
                       c.subject, c.tenant_id, c.roles_json, c.expires_at AS credential_expires_at,
                       c.revoked_at AS credential_revoked_at
                FROM browser_sessions AS s
                JOIN api_credentials AS c ON c.credential_id = s.credential_id
                WHERE s.session_digest = ?
                """,
                (self._digest(session_token),),
            ).fetchone()
        if (row is None or row["session_revoked_at"] is not None
                or row["credential_revoked_at"] is not None
                or current >= row["session_expires_at"]
                or (row["credential_expires_at"] is not None and current >= row["credential_expires_at"])):
            return None
        try:
            principal = Principal(
                row["subject"], row["tenant_id"], frozenset(json.loads(row["roles_json"]))
            )
            return BrowserSession(
                principal=principal,
                credential_id=row["credential_id"],
                csrf_digest=row["csrf_digest"],
                csrf_token=self.issue_browser_csrf_token(session_token),
                expires_at=row["session_expires_at"],
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def rotate_browser_session_csrf(self, session_token, csrf_token, now=None):
        if (not isinstance(session_token, str) or not session_token
                or not isinstance(csrf_token, str) or len(csrf_token) < 32):
            return False
        try:
            expected_csrf = self.issue_browser_csrf_token(session_token)
        except CredentialStoreUnavailable:
            return False
        if not hmac.compare_digest(csrf_token, expected_csrf):
            return False
        current = self._timestamp(now, "now")
        if current is None:
            current = time.time()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE browser_sessions
                    SET csrf_digest = ?
                    WHERE session_digest = ? AND revoked_at IS NULL AND expires_at > ?
                      AND EXISTS (
                        SELECT 1 FROM api_credentials AS c
                        WHERE c.credential_id = browser_sessions.credential_id
                          AND c.revoked_at IS NULL
                          AND (c.expires_at IS NULL OR c.expires_at > ?)
                      )
                    """,
                    (self._digest(csrf_token), self._digest(session_token), current, current),
                )
                return cursor.rowcount == 1

    def revoke_browser_session(self, session_token, now=None):
        if not isinstance(session_token, str) or not session_token:
            return False
        current = self._timestamp(now, "now")
        if current is None:
            current = time.time()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE browser_sessions SET revoked_at = ?
                    WHERE session_digest = ? AND revoked_at IS NULL
                    """,
                    (current, self._digest(session_token)),
                )
                return cursor.rowcount == 1

    def revoke(self, credential_id, actor="local-operator"):
        if not isinstance(credential_id, str) or not credential_id:
            return False
        actor = self._validate_actor(actor)
        now = time.time()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE api_credentials SET revoked_at = ?
                    WHERE credential_id = ? AND revoked_at IS NULL
                    """,
                    (now, credential_id),
                )
                if cursor.rowcount != 1:
                    return False
                row = connection.execute(
                    "SELECT subject, tenant_id, roles_json FROM api_credentials WHERE credential_id = ?",
                    (credential_id,),
                ).fetchone()
                principal = Principal(
                    row["subject"], row["tenant_id"],
                    frozenset(json.loads(row["roles_json"])),
                )
                self._record_event(
                    connection, "credential_revoked", credential_id,
                    principal, actor, now,
                )
        return True

    def rotate(self, credential_id, expires_at=None, roles=None,
               actor="local-operator"):
        """Atomically issue a replacement and revoke the old token.

        Rotation preserves the old subject and tenant. Optional roles may only
        reduce the existing role set; privilege escalation requires a separate
        explicit issue operation.
        """
        if not isinstance(credential_id, str) or not credential_id:
            raise ValueError("Wymagany jest credential_id")
        actor = self._validate_actor(actor)
        now = time.time()
        expiry_override = self._timestamp(expires_at, "expires_at")
        new_id = "cred_" + secrets.token_urlsafe(18)
        new_token = secrets.token_urlsafe(48)

        with self._connection() as connection:
            with connection:
                old = connection.execute(
                    """
                    SELECT subject, tenant_id, roles_json, expires_at, revoked_at
                    FROM api_credentials WHERE credential_id = ?
                    """,
                    (credential_id,),
                ).fetchone()
                if old is None or old["revoked_at"] is not None:
                    raise ValueError("Nie znaleziono aktywnego tokenu do rotacji")
                if old["tenant_id"] == "system":
                    raise ValueError("Rejestr tenantów nie może rotować tożsamości systemowej")
                if old["expires_at"] is not None and now >= old["expires_at"]:
                    raise ValueError("Wygasłego tokenu nie można rotować")

                old_roles = frozenset(json.loads(old["roles_json"]))
                new_roles = old_roles if roles is None else frozenset(roles)
                if not self._roles_are_non_escalating(old_roles, new_roles):
                    raise ValueError("Rotacja może zachować uprawnienia lub je ograniczyć, nie może ich zwiększać")
                principal = Principal(old["subject"], old["tenant_id"], new_roles)
                expiry = expiry_override if expiry_override is not None else old["expires_at"]
                if expiry is not None and expiry <= now:
                    raise ValueError("Nowy token musi mieć datę ważności w przyszłości")

                connection.execute(
                    """
                    INSERT INTO api_credentials
                    (credential_id, token_digest, subject, tenant_id, roles_json,
                     created_at, expires_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        new_id,
                        self._digest(new_token),
                        principal.subject,
                        principal.tenant_id,
                        json.dumps(sorted(principal.roles), separators=(",", ":")),
                        now,
                        expiry,
                    ),
                )
                connection.execute(
                    "UPDATE api_credentials SET revoked_at = ? WHERE credential_id = ?",
                    (now, credential_id),
                )
                self._record_event(
                    connection, "credential_rotated", credential_id,
                    principal, actor, now, related_credential_id=new_id,
                )
        return IssuedCredential(new_id, new_token, expiry)

    @staticmethod
    def _roles_are_non_escalating(old_roles, new_roles):
        if not new_roles or not new_roles.issubset(ALLOWED_ROLES):
            return False
        if "admin" in new_roles and "admin" not in old_roles:
            return False
        if "member" in new_roles and not ({"member", "admin"} & old_roles):
            return False
        return True

    @staticmethod
    def _has_other_active_admin(connection, tenant_id, exclude_credential_id, now):
        rows = connection.execute(
            """
            SELECT credential_id, roles_json
            FROM api_credentials
            WHERE tenant_id = ? AND credential_id != ? AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (tenant_id, exclude_credential_id, now),
        ).fetchall()
        for row in rows:
            try:
                roles = json.loads(row["roles_json"])
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CredentialStoreUnavailable("Credential role metadata is invalid") from exc
            if isinstance(roles, list) and "admin" in roles:
                return True
        return False

    def list_for_tenant(self, principal):
        """List tenant credential metadata without token digests or plaintext tokens."""
        self._require_tenant_admin(principal)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT credential_id, subject, tenant_id, roles_json,
                       created_at, expires_at, revoked_at
                FROM api_credentials
                WHERE tenant_id = ?
                ORDER BY created_at DESC, credential_id
                """,
                (principal.tenant_id,),
            ).fetchall()
        return [
            {
                "credential_id": row["credential_id"],
                "subject": row["subject"],
                "tenant_id": row["tenant_id"],
                "roles": json.loads(row["roles_json"]),
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "revoked_at": row["revoked_at"],
                "active": row["revoked_at"] is None and (
                    row["expires_at"] is None or time.time() < row["expires_at"]
                ),
            }
            for row in rows
        ]

    def issue_for_tenant(self, principal, subject, roles=None, expires_at=None):
        """Issue a tenant-bound credential; tenant ID is never caller-supplied."""
        self._require_tenant_admin(principal)
        selected_roles = frozenset({"member"} if roles is None else roles)
        new_principal = Principal(subject, principal.tenant_id, selected_roles)
        expiry = self._tenant_expiry(expires_at, time.time())
        return self.issue(new_principal, expires_at=expiry, actor=principal.subject)

    def revoke_for_tenant(self, principal, credential_id):
        """Revoke only a credential belonging to the authenticated tenant."""
        self._require_tenant_admin(principal)
        if not isinstance(credential_id, str) or not credential_id:
            return False
        now = time.time()
        with self._connection() as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT subject, tenant_id, roles_json, revoked_at
                    FROM api_credentials
                    WHERE credential_id = ? AND tenant_id = ?
                    """,
                    (credential_id, principal.tenant_id),
                ).fetchone()
                if row is None or row["revoked_at"] is not None:
                    return False
                target_roles = frozenset(json.loads(row["roles_json"]))
                if ("admin" in target_roles
                        and not self._has_other_active_admin(
                            connection, principal.tenant_id, credential_id, now
                        )):
                    raise LastTenantAdminError("Tenant musi zachować co najmniej jednego aktywnego administratora")
                cursor = connection.execute(
                    """
                    UPDATE api_credentials SET revoked_at = ?
                    WHERE credential_id = ? AND tenant_id = ? AND revoked_at IS NULL
                    """,
                    (now, credential_id, principal.tenant_id),
                )
                if cursor.rowcount != 1:
                    return False
                target = Principal(
                    row["subject"], row["tenant_id"],
                    frozenset(json.loads(row["roles_json"])),
                )
                self._record_event(
                    connection, "credential_revoked", credential_id,
                    target, principal.subject, now,
                )
        return True

    def rotate_for_tenant(self, principal, credential_id, expires_at=None, roles=None):
        """Atomically rotate only a credential within the authenticated tenant."""
        self._require_tenant_admin(principal)
        if not isinstance(credential_id, str) or not credential_id:
            raise ValueError("Wymagany jest credential_id")
        now = time.time()
        expiry_override = None if expires_at is None else self._tenant_expiry(expires_at, now)
        new_id = "cred_" + secrets.token_urlsafe(18)
        new_token = secrets.token_urlsafe(48)

        with self._connection() as connection:
            with connection:
                old = connection.execute(
                    """
                    SELECT subject, tenant_id, roles_json, expires_at, revoked_at
                    FROM api_credentials
                    WHERE credential_id = ? AND tenant_id = ?
                    """,
                    (credential_id, principal.tenant_id),
                ).fetchone()
                if old is None or old["revoked_at"] is not None:
                    raise ValueError("Nie znaleziono aktywnego tokenu w tym tenant")
                if old["expires_at"] is not None and now >= old["expires_at"]:
                    raise ValueError("Wygasłego tokenu nie można rotować")

                old_roles = frozenset(json.loads(old["roles_json"]))
                new_roles = old_roles if roles is None else frozenset(roles)
                if not self._roles_are_non_escalating(old_roles, new_roles):
                    raise ValueError("Rotacja może zachować uprawnienia lub je ograniczyć, nie może ich zwiększać")
                if ("admin" in old_roles and "admin" not in new_roles
                        and not self._has_other_active_admin(
                            connection, principal.tenant_id, credential_id, now
                        )):
                    raise LastTenantAdminError("Nie można zdegradować ostatniego aktywnego administratora")
                target = Principal(old["subject"], old["tenant_id"], new_roles)
                if expiry_override is not None:
                    expiry = expiry_override
                elif old["expires_at"] is not None:
                    expiry = min(
                        old["expires_at"],
                        now + self.TENANT_MAX_CREDENTIAL_TTL_SECONDS,
                    )
                else:
                    expiry = now + self.TENANT_DEFAULT_CREDENTIAL_TTL_SECONDS
                if expiry <= now:
                    raise ValueError("Nowy token musi mieć datę ważności w przyszłości")

                connection.execute(
                    """
                    INSERT INTO api_credentials
                    (credential_id, token_digest, subject, tenant_id, roles_json,
                     created_at, expires_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        new_id,
                        self._digest(new_token),
                        target.subject,
                        target.tenant_id,
                        json.dumps(sorted(target.roles), separators=(",", ":")),
                        now,
                        expiry,
                    ),
                )
                cursor = connection.execute(
                    """
                    UPDATE api_credentials SET revoked_at = ?
                    WHERE credential_id = ? AND tenant_id = ? AND revoked_at IS NULL
                    """,
                    (now, credential_id, principal.tenant_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Token został już zmieniony")
                self._record_event(
                    connection, "credential_rotated", credential_id,
                    target, principal.subject, now, related_credential_id=new_id,
                )
        return IssuedCredential(new_id, new_token, expiry)

    def list_audit_events(self, limit=100):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit musi należeć do zakresu 1..500")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, credential_id, related_credential_id,
                       subject, tenant_id, actor, occurred_at
                FROM credential_audit_events
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
