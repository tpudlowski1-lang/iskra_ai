"""Ensure local secrets and runtime databases are excluded by Git."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def is_ignored(path):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


class RepositoryHygieneTests(unittest.TestCase):
    def test_standard_gitignore_exists_and_legacy_filename_is_removed(self):
        self.assertTrue((ROOT / ".gitignore").is_file())
        self.assertFalse((ROOT / "gitignore").exists())

    def test_environment_secrets_are_ignored(self):
        for path in (".env", ".env.production", ".env.local"):
            with self.subTest(path=path):
                self.assertTrue(is_ignored(path))

    def test_env_example_remains_trackable(self):
        self.assertFalse(is_ignored(".env.example"))

    def test_runtime_graph_and_database_files_are_ignored(self):
        for path in (
            "wiedza.json",
            "wiedza.json.corrupt-123",
            "iskra_tenants.sqlite3",
            "credentials.sqlite3",
            "private_documents/documents.sqlite3",
            "iskra_data/wiedza.json",
            "backups/tenant-snapshot.sqlite3",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_ignored(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
