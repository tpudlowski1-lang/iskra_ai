import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.backup_iskra_data import BackupError, create_archive, restore_archive


class FullBackupArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.graph = self.root / "graph.sqlite3"
        with sqlite3.connect(self.graph) as db:
            db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO records(value) VALUES ('persisted')")
        self.knowledge = self.root / "wiedza.json"
        self.knowledge.write_text(json.dumps({"neurons": {"n": {}}, "synapses": []}), encoding="utf-8")
        self.archive = self.root / "backup.zip"

    def tearDown(self):
        self.tmp.cleanup()

    def resources(self):
        return [
            {"name": "data/graph.sqlite3", "path": str(self.graph), "kind": "sqlite"},
            {"name": "data/wiedza.json", "path": str(self.knowledge), "kind": "json"},
            {"name": "optional/documents.sqlite3", "path": str(self.root / "missing.sqlite3"),
             "kind": "sqlite", "required": False},
        ]

    def test_create_restore_round_trip_and_manifest(self):
        manifest = create_archive(self.resources(), str(self.archive), writes_paused=True)
        self.assertEqual([x["status"] for x in manifest["resources"]], ["included", "included", "absent"])
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        target = self.root / "restored"
        restored = restore_archive(str(self.archive), str(target))
        self.assertEqual(restored["format"], "iskra-backup-v1")
        self.assertEqual(json.loads((target / "data/wiedza.json").read_text())["neurons"], {"n": {}})
        with sqlite3.connect(target / "data/graph.sqlite3") as db:
            self.assertEqual(db.execute("SELECT value FROM records").fetchone()[0], "persisted")
        self.assertFalse((target / "optional/documents.sqlite3").exists())
        self.assertEqual((target / "data/graph.sqlite3").stat().st_mode & 0o777, 0o600)

    def test_restore_rejects_symlink_archive(self):
        create_archive(self.resources(), str(self.archive), writes_paused=True)
        link = self.root / "backup-link.zip"
        link.symlink_to(self.archive)
        with self.assertRaises(BackupError):
            restore_archive(str(link), str(self.root / "restore-link"))

    def test_restore_rejects_non_object_manifest(self):
        malformed = self.root / "malformed.zip"
        with zipfile.ZipFile(malformed, "w") as archive:
            archive.writestr("iskra-backup-manifest.json", "[]")
        with self.assertRaises(BackupError):
            restore_archive(str(malformed), str(self.root / "restore-malformed"))

    def test_restore_rejects_symlink_member(self):
        create_archive(self.resources(), str(self.archive), writes_paused=True)
        rewritten = self.root / "symlink-member.zip"
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(rewritten, "w") as target:
            for item in source.infolist():
                data = source.read(item.filename)
                info = zipfile.ZipInfo(item.filename)
                if item.filename == "data/wiedza.json":
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                else:
                    info.external_attr = item.external_attr
                target.writestr(info, data)
        with self.assertRaises(BackupError):
            restore_archive(str(rewritten), str(self.root / "restore-symlink-member"))

    def test_sqlite_source_path_with_reserved_uri_characters(self):
        directory = self.root / "db?set#one"
        directory.mkdir()
        database = directory / "graph.sqlite3"
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE records (value TEXT)")
            db.execute("INSERT INTO records(value) VALUES ('reserved-path')")
        archive = self.root / "reserved-path.zip"
        create_archive([{"name": "data/graph.sqlite3", "path": str(database), "kind": "sqlite"}], str(archive), writes_paused=True)
        target = self.root / "reserved-path-restore"
        restore_archive(str(archive), str(target))
        with sqlite3.connect(target / "data/graph.sqlite3") as db:
            self.assertEqual(db.execute("SELECT value FROM records").fetchone()[0], "reserved-path")

    def test_create_rejects_total_size_above_restore_limit(self):
        second = self.root / "second.json"
        second.write_text(json.dumps({"extra": "data"}), encoding="utf-8")
        resources = [
            {"name": "data/first.json", "path": str(self.knowledge), "kind": "json"},
            {"name": "data/second.json", "path": str(second), "kind": "json"},
        ]
        with patch("scripts.backup_iskra_data.MAX_ARCHIVE_BYTES", 40):
            with self.assertRaisesRegex(BackupError, "Łączny rozmiar zasobów"):
                create_archive(resources, str(self.archive), writes_paused=True)
        self.assertFalse(self.archive.exists())

    def test_requires_explicit_quiescence_acknowledgement(self):
        with self.assertRaises(BackupError):
            create_archive(self.resources(), str(self.archive), writes_paused=False)

    def test_missing_required_resource_aborts_without_archive(self):
        resources = self.resources()
        resources[0]["path"] = str(self.root / "missing-required.sqlite3")
        with self.assertRaises(BackupError):
            create_archive(resources, str(self.archive), writes_paused=True)
        self.assertFalse(self.archive.exists())

    def test_tampered_member_is_rejected(self):
        create_archive(self.resources(), str(self.archive), writes_paused=True)
        rewritten = self.root / "tampered.zip"
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(rewritten, "w") as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == "data/wiedza.json":
                    data += b" "
                target.writestr(item.filename, data)
        with self.assertRaises(BackupError):
            restore_archive(str(rewritten), str(self.root / "bad-restore"))
        self.assertFalse((self.root / "bad-restore").exists())

    def test_restore_never_overwrites_existing_target(self):
        create_archive(self.resources(), str(self.archive), writes_paused=True)
        target = self.root / "existing"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep")
        with self.assertRaises(BackupError):
            restore_archive(str(self.archive), str(target))
        self.assertEqual(marker.read_text(), "keep")

    def test_symlink_source_rejected(self):
        link = self.root / "linked.json"
        link.symlink_to(self.knowledge)
        resources = [{"name": "data/link.json", "path": str(link), "kind": "json"}]
        with self.assertRaises(BackupError):
            create_archive(resources, str(self.archive), writes_paused=True)

    def test_optional_dangling_symlink_is_rejected_not_treated_as_absent(self):
        link = self.root / "dangling.json"
        link.symlink_to(self.root / "missing-target.json")
        resources = [{
            "name": "optional/dangling.json",
            "path": str(link),
            "kind": "json",
            "required": False,
        }]
        with self.assertRaises(BackupError):
            create_archive(resources, str(self.archive), writes_paused=True)
        self.assertFalse(self.archive.exists())

    def test_resource_required_flag_must_be_boolean(self):
        resources = [{
            "name": "data/graph.sqlite3",
            "path": str(self.graph),
            "kind": "sqlite",
            "required": "false",
        }]
        with self.assertRaises(BackupError):
            create_archive(resources, str(self.archive), writes_paused=True)

    def test_archive_does_not_discover_or_include_unlisted_secrets(self):
        secret = self.root / ".env"
        secret.write_text("API_TOKEN=do-not-archive")
        create_archive(self.resources(), str(self.archive), writes_paused=True)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertNotIn(".env", archive.namelist())
            for name in archive.namelist():
                self.assertNotIn(b"do-not-archive", archive.read(name))

    def test_duplicate_and_path_traversal_names_rejected(self):
        resources = self.resources()
        resources[0]["name"] = "../escape.sqlite3"
        with self.assertRaises(BackupError):
            create_archive(resources, str(self.archive), writes_paused=True)


    def test_create_rejects_json_above_memory_limit(self):
        oversized = self.root / "oversized.json"
        oversized.write_text('{"xxx":1}', encoding="utf-8")
        with patch("scripts.backup_iskra_data.MAX_JSON_BYTES", 8):
            with self.assertRaisesRegex(BackupError, "limit"):
                create_archive(
                    [{"name": "data/oversized.json", "path": str(oversized), "kind": "json"}],
                    str(self.archive),
                    writes_paused=True,
                )
        self.assertFalse(self.archive.exists())

    def test_restore_rejects_json_above_memory_limit_before_parsing(self):
        payload = b'{"xxx":1}'
        manifest = {
            "format": "iskra-backup-v1",
            "created_at": "2026-11-23T00:00:00+00:00",
            "writes_paused_by_caller": True,
            "resources": [{
                "name": "data/oversized.json",
                "kind": "json",
                "required": True,
                "status": "included",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }
        malicious = self.root / "oversized-json.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("iskra-backup-manifest.json", json.dumps(manifest))
            archive.writestr("data/oversized.json", payload)
        target = self.root / "oversized-json-restore"
        with patch("scripts.backup_iskra_data.MAX_JSON_BYTES", 8):
            with self.assertRaisesRegex(BackupError, "limit"):
                restore_archive(str(malicious), str(target))
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
