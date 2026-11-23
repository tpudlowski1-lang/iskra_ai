"""Create and restore an explicit, private Iskra data archive.

The caller MUST stop application writes and background workers before calling
create_archive. SQLite's online backup API makes each database snapshot
consistent, but cannot make multiple independent stores share one transaction.
Only explicitly listed resources are included; secrets/configuration are never
discovered recursively.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import zipfile

MANIFEST_NAME = "iskra-backup-manifest.json"
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_RESOURCE_BYTES = 1024 * 1024 * 1024


class BackupError(RuntimeError):
    """Raised when an archive cannot be safely created or restored."""


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise BackupError("Nieprawidłowa logiczna nazwa zasobu")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise BackupError("Nazwa zasobu wychodzi poza katalog archiwum")
    if name == MANIFEST_NAME:
        raise BackupError("Nazwa zasobu jest zarezerwowana")
    return path.as_posix()


def _open_regular_nofollow(path: str):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise BackupError("Zasób musi być zwykłym plikiem")
    return os.fdopen(descriptor, "rb")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sqlite(path: Path) -> None:
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError("SQLite integrity_check nie przeszedł")
            violations = db.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise BackupError("SQLite foreign_key_check wykrył naruszenia")
    except sqlite3.DatabaseError as exc:
        raise BackupError("Zasób nie jest poprawną bazą SQLite") from exc


def _snapshot_resource(resource: dict, destination: Path) -> dict:
    name = _safe_name(resource.get("name"))
    kind = resource.get("kind")
    source = os.fspath(resource.get("path", ""))
    if kind not in ("sqlite", "json") or not source:
        raise BackupError("Zasób musi mieć kind sqlite/json i path")
    required = bool(resource.get("required", True))
    if not os.path.exists(source):
        if required:
            raise BackupError(f"Brak wymaganego zasobu: {name}")
        return {"name": name, "kind": kind, "required": False, "status": "absent"}
    if os.path.islink(source):
        raise BackupError(f"Symlink nie jest dozwolony: {name}")
    if not os.path.isfile(source):
        raise BackupError(f"Zasób nie jest zwykłym plikiem: {name}")

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if kind == "sqlite":
        try:
            source_db = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
            target_db = sqlite3.connect(destination)
            try:
                source_db.backup(target_db)
                target_db.commit()
            finally:
                target_db.close()
                source_db.close()
        except sqlite3.DatabaseError as exc:
            raise BackupError(f"Nie udało się wykonać snapshotu SQLite: {name}") from exc
        os.chmod(destination, 0o600)
        _validate_sqlite(destination)
    else:
        with _open_regular_nofollow(source) as handle:
            data = handle.read(MAX_RESOURCE_BYTES + 1)
        if len(data) > MAX_RESOURCE_BYTES:
            raise BackupError(f"Zasób przekracza limit: {name}")
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"Niepoprawny JSON: {name}") from exc
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    size = destination.stat().st_size
    if size > MAX_RESOURCE_BYTES:
        raise BackupError(f"Snapshot przekracza limit: {name}")
    return {
        "name": name,
        "kind": kind,
        "required": required,
        "status": "included",
        "size": size,
        "mode": "0600",
        "sha256": _sha256(destination),
    }


def create_archive(resources: list[dict], archive_path: str, *, writes_paused: bool) -> dict:
    """Create an archive from an explicit allowlist after writes are paused."""
    if writes_paused is not True:
        raise BackupError("Najpierw zatrzymaj zapisy aplikacji i workerów")
    if not isinstance(resources, list) or not resources:
        raise BackupError("Lista zasobów nie może być pusta")
    names = [_safe_name(item.get("name")) for item in resources]
    if len(names) != len(set(names)):
        raise BackupError("Powtórzona logiczna nazwa zasobu")
    target = Path(archive_path).absolute()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists() or target.is_symlink():
        raise BackupError("Plik archiwum już istnieje")
    os.chmod(target.parent, 0o700)
    staging = Path(tempfile.mkdtemp(prefix=".iskra-backup-", dir=target.parent))
    os.chmod(staging, 0o700)
    temporary_archive = None
    try:
        entries = []
        for resource in resources:
            name = _safe_name(resource.get("name"))
            snapshot = staging / name
            entries.append(_snapshot_resource(resource, snapshot))
        manifest = {
            "format": "iskra-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "writes_paused_by_caller": True,
            "resources": entries,
        }
        fd, temporary_archive = tempfile.mkstemp(prefix=".iskra-archive-", dir=target.parent)
        os.close(fd)
        with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, sort_keys=True).encode("utf-8"))
            for entry in entries:
                if entry["status"] == "included":
                    archive.write(staging / entry["name"], entry["name"])
        if os.path.getsize(temporary_archive) > MAX_ARCHIVE_BYTES:
            raise BackupError("Archiwum przekracza maksymalny rozmiar")
        os.chmod(temporary_archive, 0o600)
        os.link(temporary_archive, target)
        os.unlink(temporary_archive)
        temporary_archive = None
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if temporary_archive and os.path.exists(temporary_archive):
            os.unlink(temporary_archive)


def restore_archive(archive_path: str, target_dir: str) -> dict:
    """Verify and restore all archive members into a new directory atomically."""
    target = Path(target_dir).absolute()
    if target.exists() or target.is_symlink():
        raise BackupError("Katalog docelowy już istnieje — restore nie nadpisuje danych")
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(parent, 0o700)
    staging = Path(tempfile.mkdtemp(prefix=".iskra-restore-", dir=parent))
    os.chmod(staging, 0o700)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
                raise BackupError("Archiwum przekracza limit rozpakowania")
            if len([i for i in infos if i.filename == MANIFEST_NAME]) != 1:
                raise BackupError("Brak lub duplikat manifestu")
            if any(info.is_dir() or (info.external_attr >> 16) & stat.S_IFLNK for info in infos):
                raise BackupError("Katalogi i symlinki w archiwum są zabronione")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if manifest.get("format") != "iskra-backup-v1":
                raise BackupError("Nieobsługiwany format manifestu")
            entries = manifest.get("resources")
            if not isinstance(entries, list) or not entries:
                raise BackupError("Manifest nie zawiera zasobów")
            expected = {MANIFEST_NAME}
            declared_names = set()
            for entry in entries:
                name = _safe_name(entry.get("name"))
                if name in declared_names:
                    raise BackupError("Powtórzony zasób w manifeście")
                declared_names.add(name)
                if entry.get("status") == "absent":
                    if entry.get("required") is not False:
                        raise BackupError("Brak wymaganego zasobu w manifeście")
                    continue
                expected.add(name)
                if entry.get("status") != "included" or entry.get("kind") not in ("sqlite", "json"):
                    raise BackupError("Nieprawidłowy wpis manifestu")
                if entry.get("size", MAX_RESOURCE_BYTES + 1) > MAX_RESOURCE_BYTES:
                    raise BackupError("Zasób przekracza limit")
                try:
                    info = archive.getinfo(name)
                except KeyError as exc:
                    raise BackupError(f"Brak pliku w archiwum: {name}") from exc
                if info.file_size != entry["size"]:
                    raise BackupError(f"Niezgodny rozmiar zasobu: {name}")
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                data = archive.read(name)
                if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                    raise BackupError(f"Niezgodna suma SHA-256: {name}")
                descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                if entry["kind"] == "sqlite":
                    _validate_sqlite(destination)
                else:
                    try:
                        json.loads(data.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise BackupError(f"Niepoprawny JSON w archiwum: {name}") from exc
            actual = {info.filename for info in infos}
            if len(actual) != len(infos) or actual != expected:
                raise BackupError("Archiwum zawiera nieoczekiwane lub powtórzone pliki")
        os.rename(staging, target)
        return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("Niepoprawne archiwum lub manifest") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--archive", required=True)
    create.add_argument("--writes-paused", action="store_true", help="Potwierdź, że aplikacja i workery nie zapisują danych")
    create.add_argument("--json", action="append", default=[], metavar="NAME=PATH")
    create.add_argument("--sqlite", action="append", default=[], metavar="NAME=PATH")
    restore = sub.add_parser("restore")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    if args.command == "create":
        resources = []
        for kind in ("json", "sqlite"):
            for value in getattr(args, kind):
                if "=" not in value:
                    parser.error(f"--{kind} wymaga NAME=PATH")
                name, path = value.split("=", 1)
                resources.append({"name": name, "path": path, "kind": kind, "required": True})
        result = create_archive(resources, args.archive, writes_paused=args.writes_paused)
    else:
        result = restore_archive(args.archive, args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
