import os
import tempfile
import unittest

from iskra.documents.factory import DocumentRepositoryFactory
from iskra.documents.repository import SQLiteDocumentRepository
from iskra.documents.postgres_repository import PostgresDocumentRepository


class DocumentRepositoryFactoryTests(unittest.TestCase):
    def test_sqlite_is_the_default_explicit_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = DocumentRepositoryFactory(
                backend="sqlite",
                sqlite_path=os.path.join(directory, "private", "documents.sqlite3"),
            ).build()
            self.assertIsInstance(repository, SQLiteDocumentRepository)

    def test_postgres_backend_requires_dsn_and_builds_repository(self):
        with self.assertRaises(ValueError):
            DocumentRepositoryFactory(backend="postgres")
        repository = DocumentRepositoryFactory(
            backend="postgres",
            postgres_dsn="postgresql://app:secret@localhost/iskra",
        ).build()
        self.assertIsInstance(repository, PostgresDocumentRepository)

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            DocumentRepositoryFactory(backend="mysql", sqlite_path="/tmp/docs.sqlite3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
