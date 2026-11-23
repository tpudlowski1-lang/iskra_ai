"""Create tenant-scoped graph stores only from verified request principals."""
from iskra.security.principal import Principal
from iskra.storage.sqlite import SQLiteGraphStore


class TenantGraphStoreFactory:
    """Bind storage scope to a server-verified Principal, never request input."""

    def __init__(self, database_path):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("database_path musi być niepustą ścieżką")
        if database_path == ":memory:":
            raise ValueError("TenantGraphStoreFactory wymaga trwałej ścieżki")
        self._database_path = database_path

    def for_principal(self, principal):
        if not isinstance(principal, Principal):
            raise PermissionError("Brak zweryfikowanej tożsamości")
        if principal.tenant_id == "system":
            raise PermissionError("System administrator nie jest tenantem klienta")
        return SQLiteGraphStore(self._database_path, tenant_id=principal.tenant_id)
