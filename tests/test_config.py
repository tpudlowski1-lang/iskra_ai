import unittest

from iskra.config import load_settings


class RuntimeConfigurationTests(unittest.TestCase):
    def test_defaults_use_project_root_and_valid_port(self):
        settings = load_settings(environ={}, project_root="/tmp/iskra-project")
        self.assertEqual(settings.port, 10000)
        self.assertEqual(settings.data_dir, "/tmp/iskra-project")

    def test_custom_values_are_normalized(self):
        settings = load_settings(
            environ={"PORT": "8080", "DATA_DIR": "/tmp/iskra-data"},
            project_root="/unused",
        )
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.data_dir, "/tmp/iskra-data")

    def test_non_integer_port_is_rejected(self):
        with self.assertRaises(ValueError):
            load_settings(environ={"PORT": "eight"}, project_root="/tmp")

    def test_out_of_range_port_is_rejected(self):
        for value in ("0", "65536", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    load_settings(environ={"PORT": value}, project_root="/tmp")



    def test_tenant_storage_defaults_to_sqlite(self):
        settings = load_settings(environ={}, project_root="/tmp")
        self.assertEqual(settings.tenant_storage_backend, "sqlite")
        self.assertEqual(settings.postgres_dsn, "")

    def test_postgres_backend_requires_dsn(self):
        with self.assertRaises(ValueError):
            load_settings(
                environ={"ISKRA_TENANT_STORAGE_BACKEND": "postgres"},
                project_root="/tmp",
            )

    def test_postgres_backend_accepts_explicit_dsn(self):
        settings = load_settings(
            environ={
                "ISKRA_TENANT_STORAGE_BACKEND": "postgres",
                "ISKRA_POSTGRES_DSN": "postgresql://app:secret@localhost/iskra",
            },
            project_root="/tmp",
        )
        self.assertEqual(settings.tenant_storage_backend, "postgres")
        self.assertEqual(settings.postgres_dsn, "postgresql://app:secret@localhost/iskra")

    def test_document_storage_defaults_to_sqlite(self):
        settings = load_settings(environ={}, project_root="/tmp")
        self.assertEqual(settings.document_storage_backend, "sqlite")

    def test_postgres_document_backend_requires_dsn(self):
        with self.assertRaises(ValueError):
            load_settings(
                environ={"ISKRA_DOCUMENT_STORAGE_BACKEND": "postgres"},
                project_root="/tmp",
            )

    def test_postgres_document_backend_accepts_shared_dsn(self):
        settings = load_settings(
            environ={
                "ISKRA_DOCUMENT_STORAGE_BACKEND": "postgres",
                "ISKRA_POSTGRES_DSN": "postgresql://app:secret@localhost/iskra",
            },
            project_root="/tmp",
        )
        self.assertEqual(settings.document_storage_backend, "postgres")
        self.assertEqual(settings.postgres_dsn, "postgresql://app:secret@localhost/iskra")

    def test_unknown_document_storage_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            load_settings(
                environ={"ISKRA_DOCUMENT_STORAGE_BACKEND": "mysql"},
                project_root="/tmp",
            )

    def test_unknown_tenant_storage_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            load_settings(
                environ={"ISKRA_TENANT_STORAGE_BACKEND": "mysql"},
                project_root="/tmp",
            )

if __name__ == "__main__":
    unittest.main(verbosity=2)
