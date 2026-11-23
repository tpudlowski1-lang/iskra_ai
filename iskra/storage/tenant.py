"""Create tenant-scoped graph stores only from verified request principals."""
from iskra.security.principal import Principal
from iskra.storage.sqlite import SQLiteGraphStore


class TenantGraphStoreFactory:
    """Select a tenant repository while binding scope to a verified Principal."""

    def __init__(self, database_path=None, backend="sqlite", postgres_dsn=""):
        backend = str(backend).strip().lower()
        if backend not in {"sqlite", "postgres"}:
            raise ValueError("Nieobsługiwany backend tenant storage")
        self._backend = backend
        self._database_path = None
        self._postgres_dsn = ""

        if backend == "sqlite":
            if not isinstance(database_path, str) or not database_path.strip():
                raise ValueError("database_path musi być niepustą ścieżką")
            if database_path == ":memory:":
                raise ValueError("TenantGraphStoreFactory wymaga trwałej ścieżki")
            self._database_path = database_path
        else:
            if not isinstance(postgres_dsn, str) or not postgres_dsn.strip():
                raise ValueError("ISKRA_POSTGRES_DSN jest wymagany dla backendu postgres")
            self._postgres_dsn = postgres_dsn.strip()

    @property
    def backend(self):
        return self._backend

    def for_principal(self, principal):
        if not isinstance(principal, Principal):
            raise PermissionError("Brak zweryfikowanej tożsamości")
        if principal.tenant_id == "system":
            raise PermissionError("System administrator nie jest tenantem klienta")

        if self._backend == "sqlite":
            return SQLiteGraphStore(self._database_path, tenant_id=principal.tenant_id)

        # Import lazily so SQLite deployments do not require a live PostgreSQL
        # connection at application startup. The selected adapter fails closed
        # on the first operation if DSN/schema/role is not correctly provisioned.
        from iskra.storage.postgres import PostgresGraphStore
        return PostgresGraphStore(self._postgres_dsn, principal)

    def __call__(self, principal):
        """Allow Flask routes to pass the verified Principal directly."""
        return self.for_principal(principal)
