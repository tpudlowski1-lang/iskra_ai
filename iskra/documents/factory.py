"""Validated factory for the internal document repository adapters."""
import os

from iskra.documents.repository import SQLiteDocumentRepository
from iskra.documents.postgres_repository import PostgresDocumentRepository


def create_document_repository(settings):
    """Build the configured repository; SQLite remains the safe default."""
    backend = getattr(settings, "document_storage_backend", "sqlite")
    if backend == "sqlite":
        database_path = os.path.join(settings.data_dir, "iskra_documents.sqlite3")
        return SQLiteDocumentRepository(database_path)
    if backend == "postgres":
        dsn = getattr(settings, "postgres_dsn", "")
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("ISKRA_POSTGRES_DSN jest wymagany dla dokumentowego backendu postgres")
        return PostgresDocumentRepository(dsn)
    raise ValueError("Nieobsługiwany dokumentowy backend storage")
