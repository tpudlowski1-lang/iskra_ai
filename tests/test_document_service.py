import hashlib
import os
import stat
import tempfile
import unittest

from iskra.security.principal import Principal, SYSTEM_ADMIN
from iskra.documents.repository import DocumentStorageError, SQLiteDocumentRepository
from iskra.documents.service import DocumentService
from iskra.documents.parsers import parse_document
from iskra.documents.worker import parse_document_isolated, _validate_worker_payload


class TenantDocumentServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = os.path.join(self.tmp.name, "private")
        self.database = os.path.join(self.directory, "documents.sqlite3")
        self.repository = SQLiteDocumentRepository(self.database)
        self.service = DocumentService(self.repository, parser=parse_document)
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



    def test_symlink_ancestor_is_rejected_before_creating_descendants(self):
        real_root = os.path.join(self.tmp.name, "real-root")
        os.mkdir(real_root)
        linked_root = os.path.join(self.tmp.name, "linked-root")
        os.symlink(real_root, linked_root)
        database = os.path.join(linked_root, "new-private-dir", "documents.sqlite3")
        with self.assertRaises(DocumentStorageError):
            SQLiteDocumentRepository(database)
        self.assertFalse(os.path.exists(os.path.join(real_root, "new-private-dir")))

    def test_default_service_uses_isolated_parser_worker(self):
        service = DocumentService(self.repository)
        result = service.add_document(
            self.alpha, "isolated.txt", b"Tekst przetworzony w osobnym procesie."
        )
        self.assertFalse(result["duplicate"])
        self.assertEqual(len(service.list_documents(self.alpha)), 1)

    def test_isolated_parser_rejects_invalid_timeout_before_spawning(self):
        with self.assertRaises(ValueError):
            parse_document_isolated("x.txt", b"text", timeout_seconds=0)

    def test_isolated_parser_returns_safe_validation_error(self):
        with self.assertRaises(ValueError):
            parse_document_isolated("bad.pdf", b"not a pdf")


    def test_worker_payload_must_match_original_filename_and_digest(self):
        data = b"trusted source bytes"
        payload = {
            "ok": True,
            "filename": "trusted.txt",
            "extension": ".txt",
            "sha256": hashlib.sha256(data).hexdigest(),
            "chunks": ["trusted source bytes"],
        }
        parsed = _validate_worker_payload(
            payload, "trusted.txt", ".txt", hashlib.sha256(data).hexdigest()
        )
        self.assertEqual(parsed.filename, "trusted.txt")
        forged = dict(payload, sha256="0" * 64)
        with self.assertRaises(RuntimeError):
            _validate_worker_payload(
                forged, "trusted.txt", ".txt", hashlib.sha256(data).hexdigest()
            )
        renamed = dict(payload, filename="other.txt")
        with self.assertRaises(RuntimeError):
            _validate_worker_payload(
                renamed, "trusted.txt", ".txt", hashlib.sha256(data).hexdigest()
            )

    def test_worker_resource_limits_are_bounded_before_spawn(self):
        with self.assertRaises(ValueError):
            parse_document_isolated("x.txt", b"text", cpu_seconds=31)
        with self.assertRaises(ValueError):
            parse_document_isolated("x.txt", b"text", memory_limit_bytes=64 * 1024 * 1024)

    def test_isolated_parser_accepts_large_text_with_chunk_overlap(self):
        parsed = parse_document_isolated("long.txt", ("a" * 1_400_000).encode("utf-8"))
        self.assertGreater(len(parsed.chunks), 1000)
        self.assertGreater(sum(len(chunk) for chunk in parsed.chunks), 1_400_000)
        self.assertLessEqual(len(parsed.chunks), 2000)

if __name__ == "__main__":
    unittest.main(verbosity=2)
