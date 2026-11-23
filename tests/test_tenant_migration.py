import os
from pathlib import Path
import tempfile
import unittest
import uuid

from iskra.security.principal import Principal
from iskra.storage.postgres import PostgresGraphStore
from iskra.storage.sqlite import SQLiteGraphStore
from scripts.migrate_tenant_sqlite_to_postgres import (
    MigrationError,
    _validate_migration_graph,
    create_private_backup,
    migrate_snapshots,
    read_tenant_snapshots,
    sha256_file,
)


ADMIN_DSN = os.environ.get("ISKRA_TEST_POSTGRES_ADMIN_DSN")
APP_DSN = os.environ.get("ISKRA_TEST_POSTGRES_APP_DSN")


def make_graph(label):
    return {
        "neurons": {
            "node-1": {"label": label, "weight": 0.75, "created": 123.0},
            "node-2": {"label": "second", "weight": 0.4, "created": 124.0},
        },
        "synapses": [
            {"from": "node-1", "to": "node-2", "strength": 0.8}
        ],
    }


class TenantMigrationUtilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.tmp.name, "source.sqlite3")
        self.backup_dir = os.path.join(self.tmp.name, "private-backups")
        SQLiteGraphStore(self.source, "tenant-alpha").save(make_graph("alpha"))
        SQLiteGraphStore(self.source, "tenant-beta").save(make_graph("beta"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_is_consistent_private_and_hashable(self):
        backup = create_private_backup(self.source, self.backup_dir)
        self.assertTrue(os.path.isfile(backup))
        self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.backup_dir).st_mode & 0o777, 0o700)
        self.assertEqual(len(sha256_file(backup)), 64)
        snapshots = read_tenant_snapshots(backup)
        self.assertEqual(set(snapshots), {"tenant-alpha", "tenant-beta"})
        self.assertEqual(snapshots["tenant-alpha"]["neurons"]["node-1"]["label"], "alpha")

    def test_dry_run_is_default_and_does_not_require_postgres(self):
        backup = create_private_backup(self.source, self.backup_dir)
        report = migrate_snapshots(backup)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["tenant_count"], 2)
        self.assertNotIn("status", report)

    def test_out_of_range_source_values_are_rejected_without_clamping(self):
        invalid_db = os.path.join(self.tmp.name, "out-of-range.sqlite3")
        SQLiteGraphStore(invalid_db, "tenant-invalid").save(make_graph("valid"))
        import sqlite3
        with sqlite3.connect(invalid_db) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "UPDATE graph_neurons SET weight = 1.5 WHERE tenant_id = ? AND node_id = ?",
                ("tenant-invalid", "node-1"),
            )
        with self.assertRaisesRegex(MigrationError, "Kontrola integralności SQLite"):
            read_tenant_snapshots(invalid_db)
        with self.assertRaisesRegex(MigrationError, "Waga poza zakresem"):
            _validate_migration_graph(make_graph("valid") | {"neurons": {"node-1": {"label": "x", "weight": 1.5, "created": 123.0}}})

    def test_foreign_key_corruption_is_rejected_before_import(self):
        invalid_db = os.path.join(self.tmp.name, "foreign-key-invalid.sqlite3")
        SQLiteGraphStore(invalid_db, "tenant-invalid").save(make_graph("valid"))
        import sqlite3
        with sqlite3.connect(invalid_db) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO graph_synapses
                    (tenant_id, source_id, target_id, strength)
                VALUES (?, ?, ?, ?)
                """,
                ("tenant-invalid", "node-1", "missing-node", 0.5),
            )
        with self.assertRaisesRegex(MigrationError, "naruszenia kluczy obcych"):
            read_tenant_snapshots(invalid_db)

    def test_system_tenant_is_rejected(self):
        system_db = os.path.join(self.tmp.name, "system.sqlite3")
        SQLiteGraphStore(system_db, "system").save(make_graph("global"))
        with self.assertRaises(MigrationError):
            read_tenant_snapshots(system_db)

    def test_invalid_source_snapshot_is_rejected_before_postgres_access(self):
        invalid_db = os.path.join(self.tmp.name, "invalid.sqlite3")
        SQLiteGraphStore(invalid_db, "tenant-invalid").save(make_graph("valid"))
        import sqlite3
        with sqlite3.connect(invalid_db) as connection:
            connection.execute(
                """
                INSERT INTO graph_synapses
                    (tenant_id, source_id, target_id, strength)
                VALUES (?, ?, ?, ?)
                """,
                ("tenant-invalid", "node-1", "missing-node", 0.5),
            )
        with self.assertRaisesRegex(MigrationError, "naruszenia kluczy obcych"):
            read_tenant_snapshots(invalid_db)


@unittest.skipUnless(ADMIN_DSN and APP_DSN, "PostgreSQL integration service is not configured")
class TenantPostgresMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        migration_sql = (
            Path(__file__).resolve().parents[1] / "migrations" / "0001_tenant_graph.sql"
        ).read_text(encoding="utf-8")
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
            connection.execute(migration_sql, prepare=False)
            connection.execute(
                """
                GRANT USAGE ON SCHEMA public TO iskra_app_test;
                GRANT SELECT, INSERT, UPDATE, DELETE
                ON iskra_graph_neurons, iskra_graph_synapses
                TO iskra_app_test
                """,
                prepare=False,
            )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.tmp.name, "source.sqlite3")
        self.backup_dir = os.path.join(self.tmp.name, "backups")
        self.tenant_a = "mig-a-" + uuid.uuid4().hex
        self.tenant_z = "mig-z-" + uuid.uuid4().hex
        SQLiteGraphStore(self.source, self.tenant_a).save(make_graph("migrated alpha"))
        SQLiteGraphStore(self.source, self.tenant_z).save(make_graph("migrated zeta"))
        self.backup = create_private_backup(self.source, self.backup_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def store(self, tenant_id):
        principal = Principal("migration-verifier", tenant_id, frozenset({"admin"}))
        return PostgresGraphStore(APP_DSN, principal)

    def test_apply_migrates_all_tenants_and_verifies_semantic_snapshots(self):
        report = migrate_snapshots(self.backup, APP_DSN, apply=True)
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["status"], "committed_and_verified")
        self.assertEqual(report["tenant_count"], 2)
        self.assertEqual(
            self.store(self.tenant_a).load()["neurons"]["node-1"]["label"],
            "migrated alpha",
        )
        self.assertEqual(
            self.store(self.tenant_z).load()["neurons"]["node-1"]["label"],
            "migrated zeta",
        )

    def test_conflict_rolls_back_all_tenants_unless_replace_is_explicit(self):
        self.store(self.tenant_z).save(make_graph("preexisting zeta"))
        with self.assertRaises(MigrationError):
            migrate_snapshots(self.backup, APP_DSN, apply=True)
        self.assertEqual(self.store(self.tenant_a).load()["neurons"], {})
        self.assertEqual(
            self.store(self.tenant_z).load()["neurons"]["node-1"]["label"],
            "preexisting zeta",
        )

    def test_replace_existing_is_explicit_and_verified(self):
        self.store(self.tenant_a).save(make_graph("old alpha"))
        report = migrate_snapshots(
            self.backup,
            APP_DSN,
            apply=True,
            replace_existing=True,
        )
        self.assertEqual(report["status"], "committed_and_verified")
        self.assertEqual(
            self.store(self.tenant_a).load()["neurons"]["node-1"]["label"],
            "migrated alpha",
        )


if __name__ == "__main__":
    unittest.main()
