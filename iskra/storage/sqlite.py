"""Tenant-scoped transactional SQLite graph persistence.

The store is deliberately not wired into the legacy Flask app yet. A migration
must be performed explicitly after backup and staging verification.
"""
import math
import os
import sqlite3
import stat
import time
from contextlib import contextmanager

from iskra.storage.private_path import ensure_private_parent


class SQLiteGraphStore:
    """A graph repository permanently scoped to one tenant identifier."""

    def __init__(self, database_path, tenant_id):
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id musi być niepustym tekstem")
        if len(tenant_id) > 255:
            raise ValueError("tenant_id jest zbyt długi")
        if not isinstance(database_path, str) or not database_path:
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("SQLiteGraphStore wymaga trwałej ścieżki pliku")
        self.database_path = os.path.abspath(database_path)
        self._tenant_id = tenant_id.strip()
        self._prepare_private_path()
        self._initialize()

    def _prepare_private_path(self):
        """Create a private directory and reject symlink/non-regular DB paths."""
        ensure_private_parent(self.database_path)

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.database_path, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("Plik bazy grafu musi być zwykłym plikiem")
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    @property
    def tenant_id(self):
        """Read-only tenant binding; all queries are scoped to this value."""
        return self._tenant_id

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self):
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_neurons (
                    tenant_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    weight REAL NOT NULL CHECK(weight >= 0 AND weight <= 1),
                    created REAL NOT NULL,
                    PRIMARY KEY (tenant_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS graph_synapses (
                    tenant_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    strength REAL NOT NULL CHECK(strength >= 0 AND strength <= 1),
                    PRIMARY KEY (tenant_id, source_id, target_id),
                    FOREIGN KEY (tenant_id, source_id)
                        REFERENCES graph_neurons(tenant_id, node_id) ON DELETE CASCADE,
                    FOREIGN KEY (tenant_id, target_id)
                        REFERENCES graph_neurons(tenant_id, node_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_graph_synapses_tenant
                    ON graph_synapses(tenant_id);
                """
            )

    @staticmethod
    def _bounded_number(value, field):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Nieprawidłowe pole liczbowe: {field}") from None
        if not math.isfinite(number):
            raise ValueError(f"Nieprawidłowa wartość liczbowa: {field}")
        return min(max(number, 0.0), 1.0)

    @classmethod
    def _validate_graph(cls, graph):
        if not isinstance(graph, dict):
            raise ValueError("Graf musi być obiektem")
        neurons = graph.get("neurons")
        synapses = graph.get("synapses")
        if not isinstance(neurons, dict) or not isinstance(synapses, list):
            raise ValueError("Graf musi zawierać neurons i synapses")
        clean_neurons = {}
        for node_id, node in neurons.items():
            if not isinstance(node_id, str) or not node_id or len(node_id) > 160:
                raise ValueError("Nieprawidłowy identyfikator węzła")
            if not isinstance(node, dict):
                raise ValueError(f"Nieprawidłowy węzeł: {node_id}")
            label = str(node.get("label", "Nieznany"))[:500]
            weight = cls._bounded_number(node.get("weight", 0.5), "weight")
            try:
                created = float(node.get("created", time.time()))
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"Nieprawidłowy czas utworzenia: {node_id}") from None
            if not math.isfinite(created):
                raise ValueError(f"Nieprawidłowy czas utworzenia: {node_id}")
            clean_neurons[node_id] = {
                "label": label,
                "weight": weight,
                "created": created,
            }

        clean_synapses = []
        seen_edges = set()
        for edge in synapses:
            if not isinstance(edge, dict):
                raise ValueError("Synapsa musi być obiektem")
            source, target = edge.get("from"), edge.get("to")
            if (not isinstance(source, str) or not isinstance(target, str)
                    or source not in clean_neurons or target not in clean_neurons):
                raise ValueError("Synapsa wskazuje nieistniejący węzeł")
            key = (source, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            clean_synapses.append({
                "from": source,
                "to": target,
                "strength": cls._bounded_number(edge.get("strength", 0.5), "strength"),
            })
        return {"neurons": clean_neurons, "synapses": clean_synapses}

    def load(self):
        with self._connection() as connection:
            neurons = connection.execute(
                """
                SELECT node_id, label, weight, created
                FROM graph_neurons WHERE tenant_id = ? ORDER BY node_id
                """,
                (self._tenant_id,),
            ).fetchall()
            synapses = connection.execute(
                """
                SELECT source_id, target_id, strength
                FROM graph_synapses WHERE tenant_id = ?
                ORDER BY source_id, target_id
                """,
                (self._tenant_id,),
            ).fetchall()
        return {
            "neurons": {
                row["node_id"]: {
                    "label": row["label"],
                    "weight": row["weight"],
                    "created": row["created"],
                }
                for row in neurons
            },
            "synapses": [
                {"from": row["source_id"], "to": row["target_id"], "strength": row["strength"]}
                for row in synapses
            ],
        }

    def _insert_snapshot(self, connection, clean):
        """Insert a validated snapshot inside the caller's transaction."""
        connection.executemany(
            """
            INSERT INTO graph_neurons (tenant_id, node_id, label, weight, created)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (self._tenant_id, node_id, node["label"], node["weight"], node["created"])
                for node_id, node in clean["neurons"].items()
            ],
        )
        connection.executemany(
            """
            INSERT INTO graph_synapses (tenant_id, source_id, target_id, strength)
            VALUES (?, ?, ?, ?)
            """,
            [
                (self._tenant_id, edge["from"], edge["to"], edge["strength"])
                for edge in clean["synapses"]
            ],
        )

    def load_or_initialize(self, default_graph):
        """Atomically seed an empty tenant without overwriting concurrent writes."""
        clean = self._validate_graph(default_graph)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT 1 FROM graph_neurons WHERE tenant_id = ? LIMIT 1",
                    (self._tenant_id,),
                ).fetchone()
                if existing is None:
                    self._insert_snapshot(connection, clean)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.load()

    def save(self, graph):
        clean = self._validate_graph(graph)
        with self._connection() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM graph_synapses WHERE tenant_id = ?", (self._tenant_id,)
                )
                connection.execute(
                    "DELETE FROM graph_neurons WHERE tenant_id = ?", (self._tenant_id,)
                )
                connection.executemany(
                    """
                    INSERT INTO graph_neurons (tenant_id, node_id, label, weight, created)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (self._tenant_id, node_id, node["label"], node["weight"], node["created"])
                        for node_id, node in clean["neurons"].items()
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO graph_synapses (tenant_id, source_id, target_id, strength)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (self._tenant_id, edge["from"], edge["to"], edge["strength"])
                        for edge in clean["synapses"]
                    ],
                )
