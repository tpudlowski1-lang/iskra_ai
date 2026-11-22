"""Tenant-scoped transactional SQLite graph persistence.

The store is deliberately not wired into the legacy Flask app yet. A migration
must be performed explicitly after backup and staging verification.
"""
import math
import os
import sqlite3
import time


class SQLiteGraphStore:
    """A graph repository permanently scoped to one tenant identifier."""

    def __init__(self, database_path, tenant_id):
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id musi być niepustym tekstem")
        if len(tenant_id) > 255:
            raise ValueError("tenant_id jest zbyt długi")
        if not isinstance(database_path, str) or not database_path:
            raise ValueError("database_path musi być niepustą ścieżką")
        self.database_path = database_path
        self.tenant_id = tenant_id.strip()
        if database_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(database_path))
            os.makedirs(parent, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self):
        with self._connect() as connection:
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
        with self._connect() as connection:
            neurons = connection.execute(
                """
                SELECT node_id, label, weight, created
                FROM graph_neurons WHERE tenant_id = ? ORDER BY node_id
                """,
                (self.tenant_id,),
            ).fetchall()
            synapses = connection.execute(
                """
                SELECT source_id, target_id, strength
                FROM graph_synapses WHERE tenant_id = ?
                ORDER BY source_id, target_id
                """,
                (self.tenant_id,),
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

    def save(self, graph):
        clean = self._validate_graph(graph)
        with self._connect() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM graph_synapses WHERE tenant_id = ?", (self.tenant_id,)
                )
                connection.execute(
                    "DELETE FROM graph_neurons WHERE tenant_id = ?", (self.tenant_id,)
                )
                connection.executemany(
                    """
                    INSERT INTO graph_neurons (tenant_id, node_id, label, weight, created)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (self.tenant_id, node_id, node["label"], node["weight"], node["created"])
                        for node_id, node in clean["neurons"].items()
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO graph_synapses (tenant_id, source_id, target_id, strength)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (self.tenant_id, edge["from"], edge["to"], edge["strength"])
                        for edge in clean["synapses"]
                    ],
                )
