import os
from pathlib import Path
import tempfile
import unittest

from scripts.backup_iskra_data import BackupError, configured_backup_plan, main


class ConfiguredBackupPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "iskra-data"
        self.data_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **overrides):
        values = {"DATA_DIR": str(self.data_dir)}
        values.update(overrides)
        return values

    def test_default_configuration_discovers_all_local_stores(self):
        credential_db = self.data_dir / "credentials.sqlite3"
        plan = configured_backup_plan(
            self.env(ISKRA_CREDENTIAL_DB_PATH=str(credential_db)),
            project_root=str(self.root),
        )
        resources = {item["name"]: item for item in plan["resources"]}
        self.assertEqual(
            set(resources),
            {
                "legacy/wiedza.json",
                "sqlite/iskra_tenants.sqlite3",
                "sqlite/private_documents.sqlite3",
                "sqlite/credential_registry.sqlite3",
            },
        )
        self.assertEqual(resources["legacy/wiedza.json"]["path"], str(self.data_dir / "wiedza.json"))
        self.assertTrue(resources["legacy/wiedza.json"]["required"])
        self.assertTrue(resources["sqlite/credential_registry.sqlite3"]["required"])
        self.assertFalse(resources["sqlite/iskra_tenants.sqlite3"]["required"])
        self.assertFalse(resources["sqlite/private_documents.sqlite3"]["required"])
        self.assertEqual(plan["external_backends"], [])

    def test_tenant_database_override_is_respected(self):
        custom = self.root / "custom" / "tenant-store.sqlite3"
        plan = configured_backup_plan(
            self.env(ISKRA_TENANT_DB_PATH=str(custom)),
            project_root=str(self.root),
        )
        tenant = next(item for item in plan["resources"] if item["name"] == "sqlite/iskra_tenants.sqlite3")
        self.assertEqual(tenant["path"], str(custom))

    def test_postgres_backends_are_reported_and_never_silently_omitted(self):
        plan = configured_backup_plan(
            self.env(
                ISKRA_TENANT_STORAGE_BACKEND="postgres",
                ISKRA_DOCUMENT_STORAGE_BACKEND="postgres",
                ISKRA_POSTGRES_DSN="postgresql://user:secret@example.invalid/db",
            ),
            project_root=str(self.root),
        )
        self.assertEqual(
            {item["name"] for item in plan["external_backends"]},
            {"tenant_graph_postgresql", "documents_postgresql"},
        )
        self.assertNotIn("secret", repr(plan))
        self.assertNotIn("sqlite/iskra_tenants.sqlite3", {item["name"] for item in plan["resources"]})
        self.assertNotIn("sqlite/private_documents.sqlite3", {item["name"] for item in plan["resources"]})

    def test_create_from_config_fails_closed_when_postgres_is_active(self):
        with unittest.mock.patch.dict(
            os.environ,
            {
                "DATA_DIR": str(self.data_dir),
                "ISKRA_TENANT_STORAGE_BACKEND": "postgres",
                "ISKRA_POSTGRES_DSN": "postgresql://user:secret@example.invalid/db",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(BackupError, "tenant_graph_postgresql"):
                main(["create", "--from-config", "--writes-paused", "--archive", str(self.root / "backup.zip")])
        self.assertFalse((self.root / "backup.zip").exists())

    def test_plan_does_not_include_secrets_or_unknown_files(self):
        (self.data_dir / ".env").write_text("API_TOKEN=never-backup", encoding="utf-8")
        plan = configured_backup_plan(self.env(), project_root=str(self.root))
        serialized = repr(plan)
        self.assertNotIn("never-backup", serialized)
        self.assertNotIn(".env", serialized)
        self.assertEqual(len(plan["resources"]), 3)


if __name__ == "__main__":
    unittest.main()
