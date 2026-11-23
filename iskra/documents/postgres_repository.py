"""PostgreSQL document repository with transaction-local tenant RLS scope."""
from contextlib import contextmanager
import re
import time
import uuid

from iskra.documents.parsers import ParsedDocument, _safe_filename
from iskra.documents.repository import DocumentStorageError


class PostgresDocumentRepository:
    """PostgreSQL lexical document store; tenant scope is always explicit."""

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
        self._dsn = dsn
        self._connect = connect_factory

    @staticmethod
    def _validate_tenant_id(tenant_id):
        if (not isinstance(tenant_id, str) or not tenant_id.strip()
                or len(tenant_id) > 255 or tenant_id == "system"):
            raise PermissionError("Wymagany jest prawidłowy tenant scope")
        return tenant_id

    @contextmanager
    def _tenant_connection(self, tenant_id):
        tenant_id = self._validate_tenant_id(tenant_id)
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

    @staticmethod
    def _validate_document(parsed_document):
        if not isinstance(parsed_document, ParsedDocument):
            raise TypeError("Wymagany jest zweryfikowany ParsedDocument")
        safe_name, extension = _safe_filename(parsed_document.filename)
        if (
            safe_name != parsed_document.filename
            or extension != parsed_document.extension
            or not re.fullmatch(r"[0-9a-f]{64}", parsed_document.sha256 or "")
            or not parsed_document.chunks
            or len(parsed_document.chunks) > 2000
            or any(
                not isinstance(chunk, str) or not chunk or len(chunk) > 1000
                for chunk in parsed_document.chunks
            )
        ):
            raise ValueError("Nieprawidłowy snapshot dokumentu")
        return parsed_document

    def add(self, tenant_id, parsed_document):
        tenant_id = self._validate_tenant_id(tenant_id)
        parsed = self._validate_document(parsed_document)
        document_id = str(uuid.uuid4())
        try:
            with self._tenant_connection(tenant_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO iskra_documents
                            (tenant_id, document_id, filename, extension, sha256, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, sha256) DO NOTHING
                        RETURNING document_id
                        """,
                        (
                            tenant_id,
                            document_id,
                            parsed.filename,
                            parsed.extension,
                            parsed.sha256,
                            time.time(),
                        ),
                    )
                    inserted = cursor.fetchone()
                    if inserted is None:
                        cursor.execute(
                            """
                            SELECT document_id FROM iskra_documents
                            WHERE tenant_id = %s AND sha256 = %s
                            """,
                            (tenant_id, parsed.sha256),
                        )
                        existing = cursor.fetchone()
                        if existing is None:
                            raise DocumentStorageError("Nie można rozstrzygnąć duplikatu dokumentu")
                        return {
                            "document_id": existing[0],
                            "filename": parsed.filename,
                            "chunks": 0,
                            "duplicate": True,
                        }

                    cursor.executemany(
                        """
                        INSERT INTO iskra_document_chunks
                            (tenant_id, document_id, chunk_id, chunk_index, content)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (tenant_id, document_id, str(uuid.uuid4()), index, chunk)
                            for index, chunk in enumerate(parsed.chunks)
                        ],
                    )
            return {
                "document_id": document_id,
                "filename": parsed.filename,
                "chunks": len(parsed.chunks),
                "duplicate": False,
            }
        except DocumentStorageError:
            raise
        except self._database_error as exc:
            raise DocumentStorageError("Nie można zapisać dokumentu w PostgreSQL") from exc

    def list(self, tenant_id):
        tenant_id = self._validate_tenant_id(tenant_id)
        try:
            with self._tenant_connection(tenant_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT document_id, filename, extension, created_at
                        FROM iskra_documents
                        WHERE tenant_id = %s
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
        except DocumentStorageError:
            raise
        except self._database_error as exc:
            raise DocumentStorageError("Nie można odczytać dokumentów PostgreSQL") from exc

    def search(self, tenant_id, query, limit=5):
        tenant_id = self._validate_tenant_id(tenant_id)
        query = str(query or "").strip()
        if not query or len(query) > 1000:
            raise ValueError("Zapytanie musi mieć od 1 do 1000 znaków")
        if not re.search(r"[\w]{2,}", query, flags=re.UNICODE):
            return []
        try:
            safe_limit = max(1, min(int(limit), 10))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Nieprawidłowy limit wyników") from None

        try:
            with self._tenant_connection(tenant_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT d.document_id, d.filename, c.chunk_index, c.content,
                               ts_rank_cd(
                                   c.search_vector,
                                   plainto_tsquery('simple', %s)
                               ) AS score
                        FROM iskra_document_chunks AS c
                        JOIN iskra_documents AS d
                          ON d.tenant_id = c.tenant_id
                         AND d.document_id = c.document_id
                        WHERE c.tenant_id = %s
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
        except DocumentStorageError:
            raise
        except self._database_error as exc:
            raise DocumentStorageError("Nie można wyszukać dokumentów PostgreSQL") from exc

    def delete(self, tenant_id, document_id):
        tenant_id = self._validate_tenant_id(tenant_id)
        if not isinstance(document_id, str) or not document_id or len(document_id) > 64:
            raise ValueError("Nieprawidłowy identyfikator dokumentu")
        try:
            with self._tenant_connection(tenant_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM iskra_documents
                        WHERE tenant_id = %s AND document_id = %s
                        """,
                        (tenant_id, document_id),
                    )
                    return cursor.rowcount == 1
        except DocumentStorageError:
            raise
        except self._database_error as exc:
            raise DocumentStorageError("Nie można usunąć dokumentu PostgreSQL") from exc
