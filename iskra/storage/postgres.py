"""PostgreSQL graph persistence with database-enforced tenant row security."""
from contextlib import contextmanager

from iskra.security.principal import Principal
from iskra.storage.sqlite import SQLiteGraphStore


class PostgresStorageUnavailable(OSError):
    """PostgreSQL could not safely complete a tenant storage operation."""


class PostgresGraphStore:
    """A graph repository scoped to one verified principal and enforced by RLS."""

    def __init__(self, dsn, principal, connect_factory=None):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("PostgreSQL DSN musi być niepusty")
        if not isinstance(principal, Principal):
            raise PermissionError("Wymagana jest zweryfikowana tożsamość")
        if principal.tenant_id == "system":
            raise PermissionError("System administrator nie jest tenantem klienta")
        try:
            import psycopg
        except ImportError as exc:
            if connect_factory is None:
                raise RuntimeError("Zainstaluj psycopg[binary], aby używać PostgreSQL") from exc
            self._database_error = ()
        else:
            self._database_error = psycopg.Error
            if connect_factory is None:
                connect_factory = psycopg.connect
        self._dsn = dsn
        self._tenant_id = principal.tenant_id
        self._connect = connect_factory

    @property
    def tenant_id(self):
        return self._tenant_id

    @contextmanager
    def _tenant_connection(self):
        # Transaction-local context cannot leak into a later request on a pooled
        # connection. RLS denies access if this setting is absent.
        try:
            with self._connect(self._dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('iskra.tenant_id', %s, true)",
                        (self._tenant_id,),
                    )
                yield connection
        except self._database_error as exc:
            raise PostgresStorageUnavailable("PostgreSQL tenant storage unavailable") from exc

    @staticmethod
    def _insert_snapshot(cursor, tenant_id, clean):
        if clean["neurons"]:
            cursor.executemany(
                """
                INSERT INTO iskra_graph_neurons
                    (tenant_id, node_id, label, weight, created)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (tenant_id, node_id, node["label"], node["weight"], node["created"])
                    for node_id, node in clean["neurons"].items()
                ],
            )
        if clean["synapses"]:
            cursor.executemany(
                """
                INSERT INTO iskra_graph_synapses
                    (tenant_id, source_id, target_id, strength)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (tenant_id, edge["from"], edge["to"], edge["strength"])
                    for edge in clean["synapses"]
                ],
            )

    def load(self):
        with self._tenant_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT node_id, label, weight, created
                    FROM iskra_graph_neurons
                    WHERE tenant_id = %s
                    ORDER BY node_id
                    """,
                    (self._tenant_id,),
                )
                neurons = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT source_id, target_id, strength
                    FROM iskra_graph_synapses
                    WHERE tenant_id = %s
                    ORDER BY source_id, target_id
                    """,
                    (self._tenant_id,),
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

    def load_or_initialize(self, default_graph):
        """Seed an empty tenant atomically without overwriting concurrent writes."""
        clean = SQLiteGraphStore._validate_graph(default_graph)
        with self._tenant_connection() as connection:
            with connection.cursor() as cursor:
                # Serialize first-time initialization per tenant across app workers.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (self._tenant_id,),
                )
                cursor.execute(
                    """
                    SELECT 1 FROM iskra_graph_neurons
                    WHERE tenant_id = %s LIMIT 1
                    """,
                    (self._tenant_id,),
                )
                if cursor.fetchone() is None:
                    self._insert_snapshot(cursor, self._tenant_id, clean)
        return self.load()

    def save(self, graph):
        clean = SQLiteGraphStore._validate_graph(graph)
        with self._tenant_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM iskra_graph_synapses WHERE tenant_id = %s",
                    (self._tenant_id,),
                )
                cursor.execute(
                    "DELETE FROM iskra_graph_neurons WHERE tenant_id = %s",
                    (self._tenant_id,),
                )
                self._insert_snapshot(cursor, self._tenant_id, clean)
