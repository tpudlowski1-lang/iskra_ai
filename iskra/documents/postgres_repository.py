"""PostgreSQL tenant document repository with transaction-local RLS scope."""
from contextlib import contextmanager
import uuid

from iskra.documents.repository import (
    DocumentStorageError,
    SQLiteDocumentRepository,
)
from iskra.security.principal import Principal


class PostgresDocumentRepository:
    """Document repository whose every operation is bound to a verified Principal."""

    def __init__(self, dsn, connect_factory=None):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("PostgreSQL DSN musi być niepusty")
        try:
            import psycopg
        except ImportError as exc:
            if connect_factory is None:
                raise RuntimeError("Zainstaluj psycopg[binary], aby używać PostgreSQL") from exc
            self._database_error = ()
        else:
            self._database_error = psycopg.Error
            if connect_factory is None:
                connect_factory = psycopg.connect
        self._dsn = dsn.strip()
        self._connect = connect_factory

    @staticmethod
    def _tenant_id(principal):
        if not isinstance(principal, Principal):
            raise PermissionError("Wymagana jest zweryfikowana tożsamość")
        if principal.tenant_id == "system":
            raise PermissionError("System administrator nie jest tenantem klienta")
        if not principal.roles.intersection({"member", "admin"}):
            raise PermissionError("Brak uprawnień do dokumentów")
        return principal.tenant_id

    @contextmanager
    def _tenant_connection(self, principal):
        tenant_id = self._tenant_id(principal)
        try:
            with self._connect(self._dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('iskra.tenant_id', %s, true)",
                        (tenant_id,),
                    )
                yield connection
        except self._database_error as exc:
            raise DocumentStorageError("PostgreSQL document storage unavailable") from exc

    def add(self, principal, parsed_document):
        tenant_id = self._tenant_id(principal)
        SQLiteDocumentRepository._validate_parsed_document(parsed_document)
        document_id = uuid.uuid4()
        try:
            with self._tenant_connection(principal) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO iskra_tenant_documents
                            (tenant_id, document_id, filename, extension, sha256)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, sha256) DO NOTHING
                        RETURNING document_id::text
                        """,
                        (
                            tenant_id,
                            document_id,
                            parsed_document.filename,
                            parsed_document.extension,
                            parsed_document.sha256,
                        ),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        cursor.execute(
                            """
                            SELECT document_id::text
                            FROM iskra_tenant_documents
                            WHERE tenant_id=%s AND sha256=%s
                            """,
                            (tenant_id, parsed_document.sha256),
                        )
                        existing = cursor.fetchone()
                        if existing is None:
                            raise DocumentStorageError("Dokument nie został zapisany")
                        return {
                            "document_id": existing[0],
                            "filename": parsed_document.filename,
                            "chunks": 0,
                            "duplicate": True,
                        }
                    document_id_text = row[0]
                    cursor.executemany(
                        """
                        INSERT INTO iskra_tenant_document_chunks
                            (tenant_id, document_id, chunk_id, chunk_index, content)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (tenant_id, document_id, uuid.uuid4(), index, content)
                            for index, content in enumerate(parsed_document.chunks)
                        ],
                    )
            return {
                "document_id": document_id_text,
                "filename": parsed_document.filename,
                "chunks": len(parsed_document.chunks),
                "duplicate": False,
            }
        except self._database_error as exc:
            raise DocumentStorageError("Nie można zapisać dokumentu w PostgreSQL") from exc

    def list(self, principal):
        tenant_id = self._tenant_id(principal)
        try:
            with self._tenant_connection(principal) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT document_id::text, filename, extension,
                               extract(epoch FROM created_at)
                        FROM iskra_tenant_documents
                        WHERE tenant_id=%s
                        ORDER BY created_at DESC, document_id
                        """,
                        (tenant_id,),
                    )
                    rows = cursor.fetchall()
            return [
                {
                    "document_id": row[0],
                    "filename": row[1],
                    "extension": row[2],
                    "created_at": row[3],
                }
                for row in rows
            ]
        except self._database_error as exc:
            raise DocumentStorageError("Nie można odczytać dokumentów PostgreSQL") from exc

    def search(self, principal, query, limit=5):
        tenant_id = self._tenant_id(principal)
        query = str(query or "").strip()
        if not query or len(query) > 1000:
            raise ValueError("Zapytanie musi mieć od 1 do 1000 znaków")
        try:
            safe_limit = max(1, min(int(limit), 10))
        except (TypeError, ValueError):
            raise ValueError("Nieprawidłowy limit wyników") from None
        try:
            with self._tenant_connection(principal) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT d.document_id::text, d.filename, c.chunk_index, c.content,
                               ts_rank_cd(
                                   c.search_vector,
                                   plainto_tsquery('simple', %s)
                               ) AS score
                        FROM iskra_tenant_document_chunks AS c
                        JOIN iskra_tenant_documents AS d
                          ON d.tenant_id=c.tenant_id
                         AND d.document_id=c.document_id
                        WHERE c.tenant_id=%s
                          AND c.search_vector @@ plainto_tsquery('simple', %s)
                        ORDER BY score DESC, d.document_id, c.chunk_index
                        LIMIT %s
                        """,
                        (query, tenant_id, query, safe_limit),
                    )
                    rows = cursor.fetchall()
            return [
                {
                    "document_id": row[0],
                    "filename": row[1],
                    "chunk_index": row[2],
                    "excerpt": row[3][:1200],
                }
                for row in rows
            ]
        except self._database_error as exc:
            raise DocumentStorageError("Nie można przeszukać dokumentów PostgreSQL") from exc

    def delete(self, principal, document_id):
        tenant_id = self._tenant_id(principal)
        try:
            parsed_id = uuid.UUID(str(document_id))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Nieprawidłowy identyfikator dokumentu") from None
        try:
            with self._tenant_connection(principal) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM iskra_tenant_documents
                        WHERE tenant_id=%s AND document_id=%s
                        RETURNING document_id
                        """,
                        (tenant_id, parsed_id),
                    )
                    deleted = cursor.fetchone()
            return deleted is not None
        except self._database_error as exc:
            raise DocumentStorageError("Nie można usunąć dokumentu PostgreSQL") from exc
