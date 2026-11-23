"""Private SQLite document repository with tenant-scoped keys and FTS5."""
from contextlib import contextmanager
import os
import re
import sqlite3
import stat
import time
import uuid

from iskra.security.principal import Principal
from iskra.documents.parsers import (
    ALLOWED_EXTENSIONS,
    CHUNK_SIZE,
    MAX_CHUNKS,
    MAX_EXTRACTED_CHARS,
    ParsedDocument,
)


class DocumentStorageError(OSError):
    """Document repository is unavailable or failed closed."""


class SQLiteDocumentRepository:
    """Single-instance document store; never expose its database path to clients."""

    def __init__(self, database_path):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("Dokumenty wymagają trwałej, prywatnej ścieżki")
        self.database_path = os.path.abspath(database_path)
        self._prepare_private_path()
        self._initialize()

    def _prepare_private_path(self):
        parent = os.path.dirname(self.database_path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        if os.path.islink(parent) or not os.path.isdir(parent):
            raise DocumentStorageError("Katalog dokumentów musi być zwykłym katalogiem")
        os.chmod(parent, 0o700)

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.database_path, flags, 0o600)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise DocumentStorageError("Plik bazy dokumentów musi być zwykłym plikiem")
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise DocumentStorageError("Nie można bezpiecznie otworzyć bazy dokumentów") from exc

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connection = sqlite3.connect(self.database_path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA secure_delete=ON")
            yield connection
            connection.commit()
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def _initialize(self):
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        tenant_id TEXT NOT NULL CHECK(length(tenant_id) BETWEEN 1 AND 255),
                        document_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        extension TEXT NOT NULL,
                        sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
                        created_at REAL NOT NULL,
                        PRIMARY KEY (tenant_id, document_id),
                        UNIQUE (tenant_id, sha256)
                    )
                """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        tenant_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL CHECK(chunk_index >= 0),
                        content TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, chunk_id),
                        UNIQUE (tenant_id, document_id, chunk_index),
                        FOREIGN KEY (tenant_id, document_id)
                            REFERENCES documents(tenant_id, document_id)
                            ON DELETE CASCADE
                    )
                """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_documents_tenant_created
                    ON documents(tenant_id, created_at DESC)
                """)
                connection.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_fts
                    USING fts5(
                        tenant_id UNINDEXED,
                        document_id UNINDEXED,
                        chunk_id UNINDEXED,
                        filename UNINDEXED,
                        content,
                        tokenize='unicode61'
                    )
                """)
            os.chmod(self.database_path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise DocumentStorageError("Nie można zainicjalizować prywatnej bazy dokumentów") from exc

    def add(self, principal, parsed_document):
        tenant_id = self._tenant_id(principal)
        self._validate_parsed_document(parsed_document)
        document_id = str(uuid.uuid4())
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT document_id FROM documents WHERE tenant_id=? AND sha256=?",
                    (tenant_id, parsed_document.sha256),
                ).fetchone()
                if existing:
                    return {
                        "document_id": existing["document_id"],
                        "filename": parsed_document.filename,
                        "chunks": 0,
                        "duplicate": True,
                    }
                connection.execute(
                    """
                    INSERT INTO documents
                        (tenant_id, document_id, filename, extension, sha256, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        document_id,
                        parsed_document.filename,
                        parsed_document.extension,
                        parsed_document.sha256,
                        time.time(),
                    ),
                )
                for index, content in enumerate(parsed_document.chunks):
                    chunk_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO document_chunks
                            (tenant_id, document_id, chunk_id, chunk_index, content)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (tenant_id, document_id, chunk_id, index, content),
                    )
                    connection.execute(
                        """
                        INSERT INTO document_fts
                            (tenant_id, document_id, chunk_id, filename, content)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            tenant_id,
                            document_id,
                            chunk_id,
                            parsed_document.filename,
                            content,
                        ),
                    )
            return {
                "document_id": document_id,
                "filename": parsed_document.filename,
                "chunks": len(parsed_document.chunks),
                "duplicate": False,
            }
        except sqlite3.Error as exc:
            raise DocumentStorageError("Nie można zapisać dokumentu") from exc

    def list(self, principal):
        tenant_id = self._tenant_id(principal)
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT document_id, filename, extension, created_at
                    FROM documents
                    WHERE tenant_id=?
                    ORDER BY created_at DESC, document_id
                    """,
                    (tenant_id,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DocumentStorageError("Nie można odczytać listy dokumentów") from exc

    def search(self, principal, query, limit=5):
        tenant_id = self._tenant_id(principal)
        query = str(query or "").strip()
        if not query or len(query) > 1000:
            raise ValueError("Zapytanie musi mieć od 1 do 1000 znaków")
        terms = re.findall(r"[\w]{2,}", query, flags=re.UNICODE)[:20]
        if not terms:
            return []
        match_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        try:
            safe_limit = max(1, min(int(limit), 10))
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT d.document_id, d.filename, c.chunk_index, c.content,
                           bm25(document_fts) AS score
                    FROM document_fts
                    JOIN document_chunks AS c
                      ON c.tenant_id=document_fts.tenant_id
                     AND c.document_id=document_fts.document_id
                     AND c.chunk_id=document_fts.chunk_id
                    JOIN documents AS d
                      ON d.tenant_id=c.tenant_id
                     AND d.document_id=c.document_id
                    WHERE document_fts MATCH ?
                      AND document_fts.tenant_id=?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (match_query, tenant_id, safe_limit),
                ).fetchall()
            return [
                {
                    "document_id": row["document_id"],
                    "filename": row["filename"],
                    "chunk_index": row["chunk_index"],
                    "excerpt": row["content"][:1200],
                }
                for row in rows
            ]
        except (sqlite3.Error, TypeError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise
            raise DocumentStorageError("Nie można przeszukać dokumentów") from exc

    def delete(self, principal, document_id):
        tenant_id = self._tenant_id(principal)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT 1 FROM documents WHERE tenant_id=? AND document_id=?",
                    (tenant_id, document_id),
                ).fetchone()
                if row is None:
                    return False
                connection.execute(
                    "DELETE FROM document_fts WHERE tenant_id=? AND document_id=?",
                    (tenant_id, document_id),
                )
                connection.execute(
                    "DELETE FROM documents WHERE tenant_id=? AND document_id=?",
                    (tenant_id, document_id),
                )
            return True
        except sqlite3.Error as exc:
            raise DocumentStorageError("Nie można usunąć dokumentu") from exc
