"""Persistent SQLite API credential registry with atomic lifecycle audit.

Only SHA-256 digests of high-entropy bearer tokens are persisted. This is a
single-instance backend; use PostgreSQL before running multiple app instances.
"""
from contextlib import contextmanager
import os
import sqlite3
import stat

# Re-export the original public types for existing integrations.
from iskra.security.credential_store import (
    BrowserSession, CredentialStoreUnavailable, IssuedCredential, LastTenantAdminError,
    RelationalCredentialStore,
)


class SQLiteCredentialStore(RelationalCredentialStore):
    def __init__(self, database_path, csrf_secret=None):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("Rejestr wymaga trwałej ścieżki pliku")
        self.database_path = os.path.abspath(database_path)
        super().__init__(csrf_secret)
        parent = os.path.dirname(self.database_path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        self._initialize()

    @staticmethod
    def _effective_uid():
        return os.geteuid() if hasattr(os, "geteuid") else os.stat(".").st_uid

    @contextmanager
    def _connection(self, tenant_id=None, lock=False, session_digest=None):
        connection = None
        try:
            connection = sqlite3.connect(self.database_path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA foreign_keys = ON")
            # Deleted sensitive values must be overwritten in database pages.
            connection.execute("PRAGMA secure_delete = ON")
            with connection:
                if lock:
                    connection.execute("BEGIN IMMEDIATE")
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
                        # secure_delete overwrites deleted cell content in database pages.
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
                # Always flush and truncate WAL files at initialization. This also
                # makes a retry safe if a previous migration committed but could not
                # finish its checkpoint. Fail closed rather than serving with stale
                # pre-migration WAL frames that may contain plaintext CSRF values.
                checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint is not None and checkpoint[0] != 0:
                    raise sqlite3.OperationalError("Could not checkpoint credential database WAL")
        except sqlite3.Error as exc:
            raise CredentialStoreUnavailable("Credential database unavailable") from exc
