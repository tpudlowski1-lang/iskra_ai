"""Back up and migrate tenant SQLite graph snapshots to PostgreSQL.

Dry-run is the default. A real migration requires the explicit --apply flag.
All tenant snapshots are written in one PostgreSQL transaction.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile

from iskra.storage.sqlite import SQLiteGraphStore


class MigrationError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_private_backup(source_path, backup_dir):
    """Create a consistent SQLite backup using SQLite's online backup API."""
    source = os.path.abspath(source_path)
    if not os.path.isfile(source):
        raise FileNotFoundError("Źródłowa baza tenantów nie istnieje")
    destination_dir = os.path.abspath(backup_dir)
    os.makedirs(destination_dir, mode=0o700, exist_ok=True)
    os.chmod(destination_dir, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(
        destination_dir,
        f"iskra-tenant-snapshot-{stamp}-{secrets.token_hex(4)}.sqlite3",
    )
    descriptor = os.open(
        backup_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(source)) as source_db:
            with closing(sqlite3.connect(backup_path)) as backup_db:
                source_db.backup(backup_db)
        os.chmod(backup_path, 0o600)
        return backup_path
    except Exception:
        try:
            os.unlink(backup_path)
        except OSError:
            pass
        raise


def read_tenant_snapshots(sqlite_path):
    """Read and validate all tenant snapshots from a consistent SQLite copy."""
    with closing(sqlite3.connect(sqlite_path)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"graph_neurons", "graph_synapses"}.issubset(tables):
            raise MigrationError("Źródłowa baza nie zawiera schematu grafu tenantów")

        tenant_rows = connection.execute(
            "SELECT DISTINCT tenant_id FROM graph_neurons ORDER BY tenant_id"
        ).fetchall()
        snapshots = {}
        for tenant_row in tenant_rows:
            tenant_id = tenant_row["tenant_id"]
            if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id == "system":
                raise MigrationError("Źródłowa baza zawiera niedozwolony tenant_id")
            neurons = connection.execute(
                """
                SELECT node_id, label, weight, created
                FROM graph_neurons WHERE tenant_id = ? ORDER BY node_id
                """,
                (tenant_id,),
            ).fetchall()
            synapses = connection.execute(
                """
                SELECT source_id, target_id, strength
                FROM graph_synapses WHERE tenant_id = ?
                ORDER BY source_id, target_id
                """,
                (tenant_id,),
            ).fetchall()
            graph = {
                "neurons": {
                    row["node_id"]: {
                        "label": row["label"],
                        "weight": row["weight"],
                        "created": row["created"],
                    }
                    for row in neurons
                },
                "synapses": [
                    {
                        "from": row["source_id"],
                        "to": row["target_id"],
                        "strength": row["strength"],
                    }
                    for row in synapses
                ],
            }
            snapshots[tenant_id] = SQLiteGraphStore._validate_graph(graph)
    return snapshots


def _read_postgres_snapshot(cursor, tenant_id):
    cursor.execute(
        """
        SELECT node_id, label, weight, created
        FROM iskra_graph_neurons WHERE tenant_id = %s ORDER BY node_id
        """,
        (tenant_id,),
    )
    neurons = cursor.fetchall()
    cursor.execute(
        """
        SELECT source_id, target_id, strength
        FROM iskra_graph_synapses WHERE tenant_id = %s
        ORDER BY source_id, target_id
        """,
        (tenant_id,),
    )
    synapses = cursor.fetchall()
    return {
        "neurons": {
            row[0]: {"label": row[1], "weight": row[2], "created": row[3]}
            for row in neurons
        },
        "synapses": [
            {"from": row[0], "to": row[1], "strength": row[2]}
            for row in synapses
        ],
    }


def migrate_snapshots(sqlite_path, postgres_dsn=None, apply=False,
                      replace_existing=False, connect_factory=None):
    """Dry-run by default; commit every tenant together or roll back all."""
    snapshots = read_tenant_snapshots(sqlite_path)
    report = {
        "dry_run": not apply,
        "tenant_count": len(snapshots),
        "tenants": [
            {
                "tenant_id": tenant_id,
                "neurons": len(graph["neurons"]),
                "synapses": len(graph["synapses"]),
            }
            for tenant_id, graph in sorted(snapshots.items())
        ],
        "replace_existing": bool(replace_existing),
    }
    if not apply:
        if replace_existing:
            raise ValueError("--replace-existing wymaga --apply")
        return report
    if not isinstance(postgres_dsn, str) or not postgres_dsn.strip():
        raise ValueError("Brak docelowego PostgreSQL DSN")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Zainstaluj psycopg[binary], aby migrować do PostgreSQL") from exc
    connect = connect_factory or psycopg.connect

    try:
        with connect(postgres_dsn) as connection:
            with connection.cursor() as cursor:
                for tenant_id, graph in sorted(snapshots.items()):
                    cursor.execute(
                        "SELECT set_config('iskra.tenant_id', %s, true)",
                        (tenant_id,),
                    )
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM iskra_graph_neurons
                            WHERE tenant_id = %s
                        )
                        """,
                        (tenant_id,),
                    )
                    exists = cursor.fetchone()[0]
                    if exists and not replace_existing:
                        raise MigrationError(
                            f"Tenant {tenant_id} już ma dane w PostgreSQL; wymagane jawne --replace-existing"
                        )
                    if exists:
                        cursor.execute(
                            "DELETE FROM iskra_graph_synapses WHERE tenant_id = %s",
                            (tenant_id,),
                        )
                        cursor.execute(
                            "DELETE FROM iskra_graph_neurons WHERE tenant_id = %s",
                            (tenant_id,),
                        )
                    SQLiteGraphStore._validate_graph(graph)
                    cursor.executemany(
                        """
                        INSERT INTO iskra_graph_neurons
                            (tenant_id, node_id, label, weight, created)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (tenant_id, node_id, node["label"], node["weight"], node["created"])
                            for node_id, node in graph["neurons"].items()
                        ],
                    )
                    cursor.executemany(
                        """
                        INSERT INTO iskra_graph_synapses
                            (tenant_id, source_id, target_id, strength)
                        VALUES (%s, %s, %s, %s)
                        """,
                        [
                            (tenant_id, edge["from"], edge["to"], edge["strength"])
                            for edge in graph["synapses"]
                        ],
                    )
                    actual = _read_postgres_snapshot(cursor, tenant_id)
                    if actual != graph:
                        raise MigrationError(
                            f"Weryfikacja semantyczna nie powiodła się dla tenant {tenant_id}"
                        )
    except psycopg.Error as exc:
        raise MigrationError("Migracja PostgreSQL została wycofana z powodu błędu bazy") from exc

    report["dry_run"] = False
    report["status"] = "committed_and_verified"
    return report


def write_private_manifest(path, payload):
    destination = str(path)
    directory = os.path.dirname(os.path.abspath(destination))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".iskra-migration-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Ścieżka do iskra_tenants.sqlite3")
    parser.add_argument("--backup-dir", required=True, help="Prywatny katalog kopii")
    parser.add_argument("--postgres-dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--apply", action="store_true", help="Wykonaj zapis do PostgreSQL; bez tego tylko dry-run")
    parser.add_argument("--replace-existing", action="store_true", help="Jawnie zastąp istniejące grafy tenantów")
    args = parser.parse_args(argv)

    if args.replace_existing and not args.apply:
        parser.error("--replace-existing wymaga --apply")

    backup = create_private_backup(args.source, args.backup_dir)
    report = migrate_snapshots(
        backup,
        postgres_dsn=args.postgres_dsn,
        apply=args.apply,
        replace_existing=args.replace_existing,
    )
    report["backup_path"] = backup
    report["backup_sha256"] = sha256_file(backup)
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    manifest = backup + ".manifest.json"
    write_private_manifest(manifest, report)
    report["manifest_path"] = manifest
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
