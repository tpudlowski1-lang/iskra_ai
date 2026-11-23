"""Select the document repository from validated server-side storage settings."""
import os

from iskra.documents.repository import SQLiteDocumentRepository


class DocumentRepositoryFactory:
    """Build one repository implementation; tenant scope is still Principal-bound."""

    def __init__(self, backend, sqlite_path=None, postgres_dsn=""):
        backend = str(backend or "").strip().lower()
        if backend not in {"sqlite", "postgres"}:
            raise ValueError("Nieobsługiwany backend dokumentów")
        self.backend = backend
        if backend == "sqlite":
            if not isinstance(sqlite_path, str) or not sqlite_path.strip():
                raise ValueError("Wymagana jest prywatna ścieżka SQLite dokumentów")
            self._repository = SQLiteDocumentRepository(sqlite_path)
        else:
            if not isinstance(postgres_dsn, str) or not postgres_dsn.strip():
                raise ValueError("ISKRA_POSTGRES_DSN jest wymagany dla PostgreSQL")
            from iskra.documents.postgres_repository import PostgresDocumentRepository
            self._repository = PostgresDocumentRepository(postgres_dsn)

    @classmethod
    def from_settings(cls, settings):
        backend = getattr(settings, "document_storage_backend", None)
        data_dir = getattr(settings, "data_dir", None)
        postgres_dsn = getattr(settings, "postgres_dsn", "")
        sqlite_path = None
        if backend == "sqlite":
            if not isinstance(data_dir, str) or not data_dir.strip():
                raise ValueError("Brak DATA_DIR dla SQLite document storage")
            sqlite_path = os.path.join(data_dir, "private_documents", "documents.sqlite3")
        return cls(
            backend=backend,
            sqlite_path=sqlite_path,
            postgres_dsn=postgres_dsn,
        )

    def build(self):
        return self._repository
