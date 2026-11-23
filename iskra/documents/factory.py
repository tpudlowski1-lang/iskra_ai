"""Select the document repository from validated server-side storage settings."""
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

    def build(self):
        return self._repository
