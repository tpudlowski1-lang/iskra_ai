import os
import tempfile
import unittest

from iskra.config import Settings
from iskra.documents.factory import create_document_repository
from iskra.documents.postgres_repository import PostgresDocumentRepository
from iskra.documents.repository import SQLiteDocumentRepository


class DocumentRepositoryFactoryTests(unittest.TestCase):
    def test_sqlite_is_default_and_creates_private_database(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(10000, directory)
            repository = create_document_repository(settings)
            self.assertIsInstance(repository, SQLiteDocumentRepository)
            self.assertTrue(os.path.isfile(repository.database_path))
            self.assertEqual(os.stat(repository.database_path).st_mode & 0o777, 0o600)

    def test_postgres_backend_is_opt_in_and_uses_validated_dsn(self):
        settings = Settings(
            10000,
            "/tmp/iskra-data",
            tenant_storage_backend="sqlite",
            postgres_dsn="postgresql://app:secret@localhost/iskra",
            document_storage_backend="postgres",
        )
        repository = create_document_repository(settings)
        self.assertIsInstance(repository, PostgresDocumentRepository)

    def test_postgres_backend_without_dsn_is_rejected(self):
        settings = Settings(
            10000,
            "/tmp/iskra-data",
            document_storage_backend="postgres",
        )
        with self.assertRaises(ValueError):
            create_document_repository(settings)

    def test_unknown_backend_is_rejected(self):
        settings = Settings(
            10000,
            "/tmp/iskra-data",
            document_storage_backend="mysql",
        )
        with self.assertRaises(ValueError):
            create_document_repository(settings)


if __name__ == "__main__":
    unittest.main()
