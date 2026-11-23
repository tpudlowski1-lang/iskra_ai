import os
from pathlib import Path
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from iskra.documents.factory import DocumentRepositoryFactory
from iskra.documents.parsers import parse_document
from iskra.documents.service import DocumentService
from iskra.security.principal import Principal, SYSTEM_ADMIN


ADMIN_DSN = os.environ.get("ISKRA_TEST_POSTGRES_ADMIN_DSN")
APP_DSN = os.environ.get("ISKRA_TEST_POSTGRES_APP_DSN")


@unittest.skipUnless(ADMIN_DSN and APP_DSN, "PostgreSQL integration service is not configured")
class PostgresDocumentRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        root = Path(__file__).resolve().parents[1]
        migrations = [
            (root / "migrations" / "0001_tenant_graph.sql").read_text(encoding="utf-8"),
            (root / "migrations" / "0002_tenant_documents.sql").read_text(encoding="utf-8"),
        ]
        with psycopg.connect(ADMIN_DSN) as connection:
            connection.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iskra_app_test') THEN
                        CREATE ROLE iskra_app_test LOGIN PASSWORD 'iskra_test_password'
                            NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END;
                $$
                """
            )
            connection.execute(
                "ALTER ROLE iskra_app_test WITH LOGIN PASSWORD 'iskra_test_password' NOSUPERUSER NOBYPASSRLS"
            )
            for migration in migrations:
                connection.execute(migration, prepare=False)
            connection.execute(
                """
                GRANT USAGE ON SCHEMA public TO iskra_app_test;
                GRANT SELECT, INSERT, UPDATE, DELETE
                ON iskra_graph_neurons, iskra_graph_synapses,
                   iskra_tenant_documents, iskra_tenant_document_chunks
                TO iskra_app_test
                """,
                prepare=False,
            )

    def setUp(self):
        suffix = uuid.uuid4().hex
        self.alpha = Principal("alice", "tenant-alpha-" + suffix, frozenset({"member"}))
        self.beta = Principal("bob", "tenant-beta-" + suffix, frozenset({"member"}))
        repository = DocumentRepositoryFactory(
            backend="postgres",
            postgres_dsn=APP_DSN,
        ).build()
        self.service = DocumentService(repository, parser=parse_document)

    def test_principal_is_required_and_system_admin_is_rejected(self):
        repository = DocumentRepositoryFactory(
            backend="postgres",
            postgres_dsn=APP_DSN,
        ).build()
        with self.assertRaises(PermissionError):
            repository.list(None)
        with self.assertRaises(PermissionError):
            repository.list(SYSTEM_ADMIN)

    def test_two_tenants_are_isolated_for_list_search_and_delete(self):
        alpha = self.service.add_document(
            self.alpha, "alpha.txt", b"Dokument prywatny ALFA-440."
        )
        beta = self.service.add_document(
            self.beta, "beta.txt", b"Dokument prywatny BETA-550."
        )
        self.assertEqual(len(self.service.list_documents(self.alpha)), 1)
        self.assertEqual(len(self.service.list_documents(self.beta)), 1)
        self.assertEqual(len(self.service.search_documents(self.alpha, "ALFA-440")), 1)
        self.assertEqual(self.service.search_documents(self.alpha, "BETA-550"), [])
        self.assertEqual(len(self.service.search_documents(self.beta, "BETA-550")), 1)
        self.assertEqual(self.service.search_documents(self.beta, "ALFA-440"), [])
        self.assertFalse(self.service.delete_document(self.alpha, beta["document_id"]))
        self.assertEqual(len(self.service.list_documents(self.beta)), 1)
        self.assertTrue(self.service.delete_document(self.alpha, alpha["document_id"]))
        self.assertEqual(self.service.list_documents(self.alpha), [])

    def test_duplicate_detection_is_tenant_scoped(self):
        data = b"Unikalna tresc do testu PostgreSQL dedup 83921."
        first = self.service.add_document(self.alpha, "first.txt", data)
        duplicate = self.service.add_document(self.alpha, "renamed.txt", data)
        other_tenant = self.service.add_document(self.beta, "same.txt", data)
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["document_id"], duplicate["document_id"])
        self.assertFalse(other_tenant["duplicate"])
        self.assertNotEqual(first["document_id"], other_tenant["document_id"])

    def test_concurrent_duplicate_uploads_commit_only_one_document(self):
        data = b"Concurrent document insertion unique 592814."
        barrier = threading.Barrier(2)

        def add():
            barrier.wait(timeout=5)
            return self.service.add_document(self.alpha, "parallel.txt", data)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: add(), range(2)))
        self.assertEqual(len({result["document_id"] for result in results}), 1)
        self.assertEqual(sum(not result["duplicate"] for result in results), 1)
        self.assertEqual(len(self.service.list_documents(self.alpha)), 1)

    def test_database_rls_blocks_cross_tenant_reads_and_writes(self):
        self.service.add_document(self.alpha, "alpha.txt", b"Alpha only source.")
        beta = self.service.add_document(self.beta, "beta.txt", b"Beta only source.")
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('iskra.tenant_id', %s, true)",
                    (self.alpha.tenant_id,),
                )
                cursor.execute(
                    "SELECT tenant_id, document_id FROM iskra_tenant_documents WHERE tenant_id=%s",
                    (self.beta.tenant_id,),
                )
                self.assertEqual(cursor.fetchall(), [])
                cursor.execute(
                    "SELECT tenant_id, chunk_id FROM iskra_tenant_document_chunks WHERE tenant_id=%s",
                    (self.beta.tenant_id,),
                )
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_tenant_documents
                            (tenant_id, document_id, filename, extension, sha256)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            self.beta.tenant_id,
                            uuid.uuid4(),
                            "attack.txt",
                            ".txt",
                            "a" * 64,
                        ),
                    )
                connection.rollback()
        self.assertEqual(len(self.service.list_documents(self.beta)), 1)
        self.assertEqual(beta["filename"], "beta.txt")

    def test_missing_tenant_context_fails_closed(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT tenant_id FROM iskra_tenant_documents")
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_tenant_documents
                            (tenant_id, document_id, filename, extension, sha256)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        ("tenant-no-context", uuid.uuid4(), "x.txt", ".txt", "b" * 64),
                    )
                connection.rollback()

    def test_runtime_role_is_not_superuser_or_bypassrls(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
                )
                self.assertEqual(cursor.fetchone(), (False, False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
