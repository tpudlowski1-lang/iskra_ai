"""Create and restore an explicit, private Iskra data archive.

The caller MUST stop application writes and background workers before calling
create_archive. SQLite's online backup API makes each database snapshot
consistent, but cannot make multiple independent stores share one transaction.
Only explicitly listed resources are included; secrets/configuration are never
discovered recursively.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
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
MAX_MANIFEST_BYTES = 1024 * 1024
# JSON parsing materializes the document in memory; keep it well below SQLite/archive limits.
MAX_JSON_BYTES = 64 * 1024 * 1024


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
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BackupError("Zasób nie może być bezpiecznie otwarty") from exc
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


def _sqlite_readonly_uri(path: Path) -> str:
    """Return an escaped read-only SQLite URI for paths with reserved characters."""
    return path.resolve().as_uri() + "?mode=ro"


def _validate_sqlite(path: Path) -> None:
    try:
        with sqlite3.connect(_sqlite_readonly_uri(path), uri=True) as db:
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
    required_value = resource.get("required", True)
    if not isinstance(required_value, bool):
        raise BackupError("Pole required musi być wartością logiczną")
    required = required_value
    if os.path.islink(source):
        raise BackupError(f"Symlink nie jest dozwolony: {name}")
    if not os.path.exists(source):
        if required:
            raise BackupError(f"Brak wymaganego zasobu: {name}")
        return {"name": name, "kind": kind, "required": False, "status": "absent"}
    if not os.path.isfile(source):
        raise BackupError(f"Zasób nie jest zwykłym plikiem: {name}")

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if kind == "sqlite":
        try:
            source_db = sqlite3.connect(_sqlite_readonly_uri(Path(source)), uri=True)
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
        with destination.open("rb") as snapshot_file:
            os.fsync(snapshot_file.fileno())
        _validate_sqlite(destination)
    else:
        with _open_regular_nofollow(source) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_JSON_BYTES:
                raise BackupError(f"Plik JSON przekracza limit pamięciowy: {name}")
            data = handle.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise BackupError(f"Plik JSON przekracza limit pamięciowy: {name}")
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
    if any(not isinstance(item, dict) for item in resources):
        raise BackupError("Każdy zasób musi być obiektem konfiguracji")
    names = [_safe_name(item.get("name")) for item in resources]
    if len(names) != len(set(names)):
        raise BackupError("Powtórzona logiczna nazwa zasobu")
    target = Path(archive_path).absolute()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists() or target.is_symlink():
        raise BackupError("Plik archiwum już istnieje")
    staging = Path(tempfile.mkdtemp(prefix=".iskra-backup-", dir=target.parent))
    os.chmod(staging, 0o700)
    temporary_archive = None
    try:
        entries = []
        for resource in resources:
            name = _safe_name(resource.get("name"))
            snapshot = staging / name
            entries.append(_snapshot_resource(resource, snapshot))
        # Keep the archive creatable and restorable under the same extraction
        # limit; otherwise highly compressible inputs could create an archive
        # that this tool itself later refuses to restore.
        total_resource_bytes = sum(
            entry.get("size", 0) for entry in entries if entry["status"] == "included"
        )
        if total_resource_bytes > MAX_ARCHIVE_BYTES:
            raise BackupError("Łączny rozmiar zasobów przekracza limit archiwum")
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
        with open(temporary_archive, "rb") as archive_file:
            os.fsync(archive_file.fileno())
        os.link(temporary_archive, target)
        os.unlink(temporary_archive)
        temporary_archive = None
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if temporary_archive and os.path.exists(temporary_archive):
            os.unlink(temporary_archive)


def _publish_directory_noreplace(staging: Path, target: Path) -> None:
    """Atomically publish a directory without replacing an existing path."""
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise BackupError("System nie udostępnia atomowej publikacji katalogu bez nadpisania")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(staging), -100, os.fsencode(target), 1)
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise BackupError("Katalog docelowy już istnieje — restore nie nadpisuje danych")
        raise OSError(error, os.strerror(error), str(target))


def restore_archive(archive_path: str, target_dir: str) -> dict:
    """Verify and restore all archive members into a new directory atomically."""
    target = Path(target_dir).absolute()
    if target.exists() or target.is_symlink():
        raise BackupError("Katalog docelowy już istnieje — restore nie nadpisuje danych")
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".iskra-restore-", dir=parent))
    os.chmod(staging, 0o700)
    try:
        with _open_regular_nofollow(archive_path) as archive_handle, zipfile.ZipFile(archive_handle, "r") as archive:
            infos = archive.infolist()
            if os.fstat(archive_handle.fileno()).st_size > MAX_ARCHIVE_BYTES:
                raise BackupError("Plik archiwum przekracza maksymalny rozmiar")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
                raise BackupError("Archiwum przekracza limit rozpakowania")
            manifests = [i for i in infos if i.filename == MANIFEST_NAME]
            if len(manifests) != 1:
                raise BackupError("Brak lub duplikat manifestu")
            if any(
                info.is_dir()
                or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                for info in infos
            ):
                raise BackupError("Katalogi i pliki specjalne w archiwum są zabronione")
            if manifests[0].file_size > MAX_MANIFEST_BYTES:
                raise BackupError("Manifest przekracza maksymalny rozmiar")
            manifest = json.loads(archive.read(manifests[0]).decode("utf-8"))
            if not isinstance(manifest, dict):
                raise BackupError("Manifest musi być obiektem JSON")
            if manifest.get("format") != "iskra-backup-v1":
                raise BackupError("Nieobsługiwany format manifestu")
            entries = manifest.get("resources")
            if not isinstance(entries, list) or not entries:
                raise BackupError("Manifest nie zawiera zasobów")
            expected = {MANIFEST_NAME}
            declared_names = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise BackupError("Wpis manifestu musi być obiektem")
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
                size = entry.get("size", MAX_RESOURCE_BYTES + 1)
                if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_RESOURCE_BYTES:
                    raise BackupError("Nieprawidłowy rozmiar zasobu")
                if entry.get("kind") == "json" and size > MAX_JSON_BYTES:
                    raise BackupError("Plik JSON przekracza limit pamięciowy")
                try:
                    info = archive.getinfo(name)
                except KeyError as exc:
                    raise BackupError(f"Brak pliku w archiwum: {name}") from exc
                if info.file_size != entry["size"]:
                    raise BackupError(f"Niezgodny rozmiar zasobu: {name}")
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if info.file_size > MAX_RESOURCE_BYTES:
                    raise BackupError(f"Zasób przekracza limit: {name}")
                digest = hashlib.sha256()
                total = 0
                descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with archive.open(info, "r") as source_handle, os.fdopen(descriptor, "wb") as output:
                    for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                        total += len(chunk)
                        limit = MAX_JSON_BYTES if entry["kind"] == "json" else MAX_RESOURCE_BYTES
                        if total > limit:
                            raise BackupError(f"Zasób przekracza limit: {name}")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if total != entry["size"] or digest.hexdigest() != entry.get("sha256"):
                    raise BackupError(f"Niezgodny rozmiar lub suma SHA-256: {name}")
                if entry["kind"] == "sqlite":
                    _validate_sqlite(destination)
                else:
                    try:
                        with destination.open("r", encoding="utf-8") as json_handle:
                            json.load(json_handle)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise BackupError(f"Niepoprawny JSON w archiwum: {name}") from exc
            actual = {info.filename for info in infos}
            if len(actual) != len(infos) or actual != expected:
                raise BackupError("Archiwum zawiera nieoczekiwane lub powtórzone pliki")
        _publish_directory_noreplace(staging, target)
        try:
            parent_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError:
            pass
        return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
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
