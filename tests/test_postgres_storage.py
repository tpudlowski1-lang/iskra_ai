import os
from pathlib import Path
import unittest
from uuid import uuid4

from iskra.security.principal import Principal, SYSTEM_ADMIN
from iskra.storage.postgres import PostgresGraphStore


ADMIN_DSN = os.environ.get("ISKRA_TEST_POSTGRES_ADMIN_DSN")
APP_DSN = os.environ.get("ISKRA_TEST_POSTGRES_APP_DSN")


@unittest.skipUnless(ADMIN_DSN and APP_DSN, "PostgreSQL integration service is not configured")
class PostgresGraphStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        migration_dir = Path(__file__).resolve().parents[1] / "migrations"
        migration_sql = [
            (migration_dir / "0001_tenant_graph.sql").read_text(encoding="utf-8"),
            (migration_dir / "0002_tenant_documents.sql").read_text(encoding="utf-8"),
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
            for migration in migration_sql:
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
        suffix = uuid4().hex
        self.alpha = Principal("alice", "tenant-alpha-" + suffix, frozenset({"member"}))
        self.beta = Principal("bob", "tenant-beta-" + suffix, frozenset({"member"}))
        self.alpha_store = PostgresGraphStore(APP_DSN, self.alpha)
        self.beta_store = PostgresGraphStore(APP_DSN, self.beta)

    @staticmethod
    def graph(label):
        return {
            "neurons": {
                "node-1": {"label": label, "weight": 0.8, "created": 123.0}
            },
            "synapses": [],
        }

    def test_principal_is_required_and_system_admin_is_not_a_customer_tenant(self):
        with self.assertRaises(PermissionError):
            PostgresGraphStore(APP_DSN, {"tenant_id": "tenant-alpha"})
        with self.assertRaises(PermissionError):
            PostgresGraphStore(APP_DSN, SYSTEM_ADMIN)

    def test_two_tenants_are_isolated_by_store_and_database(self):
        self.alpha_store.save(self.graph("alpha private"))
        self.beta_store.save(self.graph("beta private"))
        self.assertEqual(
            self.alpha_store.load()["neurons"]["node-1"]["label"],
            "alpha private",
        )
        self.assertEqual(
            self.beta_store.load()["neurons"]["node-1"]["label"],
            "beta private",
        )

    def test_load_or_initialize_seeds_each_tenant_once(self):
        self.alpha_store.load_or_initialize(self.graph("alpha seed"))
        self.alpha_store.load_or_initialize(self.graph("replacement seed"))
        self.beta_store.load_or_initialize(self.graph("beta seed"))
        self.assertEqual(
            self.alpha_store.load()["neurons"]["node-1"]["label"],
            "alpha seed",
        )
        self.assertEqual(
            self.beta_store.load()["neurons"]["node-1"]["label"],
            "beta seed",
        )

    def test_rls_blocks_cross_tenant_reads_and_writes_even_with_direct_sql(self):
        self.beta_store.save(self.graph("private fixture"))
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('iskra.tenant_id', %s, true)",
                    (self.alpha.tenant_id,),
                )
                cursor.execute(
                    "SELECT tenant_id, node_id FROM iskra_graph_neurons WHERE tenant_id = %s",
                    (self.beta.tenant_id,),
                )
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_graph_neurons
                            (tenant_id, node_id, label, weight, created)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (self.beta.tenant_id, "attack-node", "attack", 0.2, 123.0),
                    )
                connection.rollback()

    def test_missing_tenant_context_fails_closed_at_database_layer(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT tenant_id FROM iskra_graph_neurons")
                self.assertEqual(cursor.fetchall(), [])
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        INSERT INTO iskra_graph_neurons
                            (tenant_id, node_id, label, weight, created)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (self.alpha.tenant_id, "no-context", "blocked", 0.2, 123.0),
                    )
                connection.rollback()

    def test_runtime_database_role_is_not_superuser_or_bypassrls(self):
        with self.psycopg.connect(APP_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rolsuper, rolbypassrls
                    FROM pg_roles WHERE rolname = current_user
                    """
                )
                self.assertEqual(cursor.fetchone(), (False, False))


if __name__ == "__main__":
    unittest.main()
