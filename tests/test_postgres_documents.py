import os
from pathlib import Path
import unittest
import uuid

from iskra.security.principal import Principal, SYSTEM_ADMIN
from iskra.documents.parsers import parse_document
from iskra.documents.postgres_repository import PostgresDocumentRepository
from iskra.documents.service import DocumentService


ADMIN_DSN = os.environ.get("ISKRA_TEST_POSTGRES_ADMIN_DSN")
APP_DSN = os.environ.get("ISKRA_TEST_POSTGRES_APP_DSN")


@unittest.skipUnless(ADMIN_DSN and APP_DSN, "PostgreSQL integration service is not configured")
class PostgresDocumentRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        root = Path(__file__).resolve().parents[1]
        graph_migration = (root / "migrations" / "0001_tenant_graph.sql").read_text(encoding="utf-8")
        document_migration = (root / "migrations" / "0002_tenant_documents.sql").read_text(encoding="utf-8")
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
            connection.execute(graph_migration, prepare=False)
            connection.execute(document_migration, prepare=False)
            connection.execute(
                """
                GRANT USAGE ON SCHEMA public TO iskra_app_test;
                GRANT SELECT, INSERT, UPDATE, DELETE
                ON iskra_tenant_documents, iskra_tenant_document_chunks
                TO iskra_app_test
                """,
                prepare=False,
            )

    def setUp(self):
        self.tenant_alpha = "doc-a-" + uuid.uuid4().hex
        self.tenant_beta = "doc-b-" + uuid.uuid4().hex
        self.alpha = Principal("doc-member-a", self.tenant_alpha, frozenset({"member"}))
        self.beta = Principal("doc-member-b", self.tenant_beta, frozenset({"member"}))
        self.repository = PostgresDocumentRepository(APP_DSN)
        self.service = DocumentService(self.repository, parser=parse_document)

    def test_tenant_scoped_add_search_list_and_delete(self):
        alpha = self.service.add_document(
            self.alpha, "alpha.txt", "Poufna oferta ALFA-440 dla najemcy.".encode("utf-8")
        )
        beta = self.service.add_document(
            self.beta, "beta.txt", "Poufna oferta BETA-550 dla najemcy.".encode("utf-8")
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

    def test_duplicate_detection_is_scoped_to_tenant(self):
        data = "Ta sama treść dokumentu dla dwóch różnych tenantów.".encode("utf-8")
        first = self.service.add_document(self.alpha, "first.txt", data)
        duplicate = self.service.add_document(self.alpha, "renamed.txt", data)
        other_tenant = self.service.add_document(self.beta, "same.txt", data)
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["document_id"], first["document_id"])
        self.assertFalse(other_tenant["duplicate"])
        self.assertNotEqual(other_tenant["document_id"], first["document_id"])

    def test_rls_blocks_cross_tenant_reads_and_writes(self):
        self.service.add_document(self.alpha, "alpha.txt", b"ALPHA secret phrase")
        self.service.add_document(self.beta, "beta.txt", b"BETA secret phrase")
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('iskra.tenant_id', %s, true)",
                    (self.tenant_alpha,),
                )
                cursor.execute(
                    "SELECT tenant_id, filename FROM iskra_tenant_documents WHERE tenant_id = %s",
                    (self.tenant_beta,),
                )
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_tenant_documents
                            (tenant_id, document_id, filename, extension, sha256, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            self.tenant_beta,
                            uuid.uuid4(),
                            "forged.txt",
                            ".txt",
                            "a" * 64,
                        ),
                    )
                connection.rollback()

    def test_missing_tenant_context_fails_closed(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT tenant_id FROM iskra_tenant_documents")
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_documents
                            (tenant_id, document_id, filename, extension, sha256, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            self.tenant_alpha,
                            uuid.uuid4(),
                            "no-context.txt",
                            ".txt",
                            "b" * 64,
                        ),
                    )
                connection.rollback()

    def test_document_tables_force_row_level_security(self):
        with self.psycopg.connect(ADMIN_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT relrowsecurity, relforcerowsecurity
                    FROM pg_class WHERE relname = 'iskra_tenant_documents'
                    """
                )
                self.assertEqual(cursor.fetchone(), (True, True))
                cursor.execute(
                    """
                    SELECT relrowsecurity, relforcerowsecurity
                    FROM pg_class WHERE relname = 'iskra_tenant_document_chunks'
                    """
                )
                self.assertEqual(cursor.fetchone(), (True, True))

    def test_runtime_role_is_not_superuser_or_bypassrls(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
                self.assertEqual(cursor.fetchone(), (False, False))

    def test_system_principal_and_invalid_tenant_scope_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.service.list_documents(SYSTEM_ADMIN)
        with self.assertRaises(PermissionError):
            self.repository.list(SYSTEM_ADMIN)
        with self.assertRaises(PermissionError):
            self.repository.list(None)

    def test_search_query_is_parameterized_and_bounded(self):
        self.service.add_document(self.alpha, "safe.txt", b"Safe document content for query testing.")
        self.assertEqual(
            self.service.search_documents(self.alpha, "x'); DROP TABLE iskra_tenant_documents; --"),
            [],
        )
        with self.assertRaises(ValueError):
            self.service.search_documents(self.alpha, "")
        with self.assertRaises(ValueError):
            self.service.search_documents(self.alpha, "x" * 1001)
        self.assertEqual(len(self.service.list_documents(self.alpha)), 1)

    def test_document_migration_is_idempotent(self):
        migration_sql = (
            Path(__file__).resolve().parents[1] / "migrations" / "0002_tenant_documents.sql"
        ).read_text(encoding="utf-8")
        with self.psycopg.connect(ADMIN_DSN) as connection:
            connection.execute(migration_sql, prepare=False)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
