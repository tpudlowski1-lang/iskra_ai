import os
import stat
import tempfile
import unittest

from iskra.security.principal import Principal, SYSTEM_ADMIN
from iskra.documents.repository import DocumentStorageError, SQLiteDocumentRepository
from iskra.documents.service import DocumentService


class TenantDocumentServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = os.path.join(self.tmp.name, "private")
        self.database = os.path.join(self.directory, "documents.sqlite3")
        self.repository = SQLiteDocumentRepository(self.database)
        self.service = DocumentService(self.repository)
        self.alpha = Principal("member-a", "tenant-alpha", frozenset({"member"}))
        self.beta = Principal("member-b", "tenant-beta", frozenset({"member"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_database_directory_and_file_permissions_are_private(self):
        directory_mode = stat.S_IMODE(os.stat(self.directory).st_mode)
        file_mode = stat.S_IMODE(os.stat(self.database).st_mode)
        self.assertEqual(directory_mode, 0o700)
        self.assertEqual(file_mode, 0o600)

    def test_tenant_scoped_add_search_list_and_delete(self):
        alpha = self.service.add_document(
            self.alpha, "oferta-alpha.txt", b"Poufna oferta ALFA-440 dla klienta."
        )
        beta = self.service.add_document(
            self.beta, "oferta-beta.txt", b"Poufna oferta BETA-550 dla klienta."
        )

        self.assertEqual(len(self.service.list_documents(self.alpha)), 1)
        self.assertEqual(len(self.service.list_documents(self.beta)), 1)
        self.assertEqual(
            len(self.service.search_documents(self.alpha, "ALFA-440")), 1
        )
        self.assertEqual(
            self.service.search_documents(self.alpha, "BETA-550"), []
        )
        self.assertEqual(
            len(self.service.search_documents(self.beta, "BETA-550")), 1
        )
        self.assertEqual(
            self.service.search_documents(self.beta, "ALFA-440"), []
        )

        self.assertFalse(self.service.delete_document(self.alpha, beta["document_id"]))
        self.assertEqual(len(self.service.list_documents(self.beta)), 1)
        self.assertTrue(self.service.delete_document(self.alpha, alpha["document_id"]))
        self.assertEqual(self.service.list_documents(self.alpha), [])

    def test_duplicate_document_is_deduplicated_only_inside_same_tenant(self):
        first = self.service.add_document(self.alpha, "first.txt", "Treść do deduplikacji.".encode("utf-8"))
        duplicate = self.service.add_document(self.alpha, "renamed.txt", "Treść do deduplikacji.".encode("utf-8"))
        other_tenant = self.service.add_document(self.beta, "same.txt", "Treść do deduplikacji.".encode("utf-8"))
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["document_id"], first["document_id"])
        self.assertFalse(other_tenant["duplicate"])
        self.assertNotEqual(other_tenant["document_id"], first["document_id"])

    def test_system_admin_and_unverified_identity_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.service.list_documents(SYSTEM_ADMIN)
        with self.assertRaises(PermissionError):
            self.service.add_document(None, "x.txt", b"data")

    def test_invalid_query_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.search_documents(self.alpha, "")
        with self.assertRaises(ValueError):
            self.service.search_documents(self.alpha, "x" * 1001)

    def test_symlink_database_path_is_rejected(self):
        target = os.path.join(self.tmp.name, "target.sqlite3")
        SQLiteDocumentRepository(target)
        link = os.path.join(self.tmp.name, "linked.sqlite3")
        os.symlink(target, link)
        with self.assertRaises((DocumentStorageError, OSError)):
            SQLiteDocumentRepository(link)


if __name__ == "__main__":
    unittest.main(verbosity=2)
