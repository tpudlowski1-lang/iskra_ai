"""Iskra PostgreSQL credential registry. The web process has no operator role."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout, TooManyRequests

from iskra.security.credential_store import CredentialStoreUnavailable, RelationalCredentialStore


class _StatementExecutor:
    """Adapt DB-API qmark parameters in the shared, static credential statements."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        return self.connection.execute(statement.replace("?", "%s"), parameters)


class PostgresCredentialStore(RelationalCredentialStore):
    credential_lookup = "SELECT * FROM iskra_auth.lookup_credential(?)"
    session_lookup = "SELECT * FROM iskra_auth.lookup_session(?)"

    def __init__(self, dsn, csrf_secret, *, operator=False):
        super().__init__(csrf_secret)
        if not dsn or (not operator and not self.csrf_secret):
            raise ValueError("PostgreSQL credentials require an explicit DSN and browser signing secret")
        self.pool = ConnectionPool(
            dsn, min_size=0, max_size=4, max_waiting=16, timeout=4, open=False,
            check=ConnectionPool.check_connection,
            kwargs={"row_factory": dict_row, "connect_timeout": 3,
                    "options": "-c search_path=pg_catalog,iskra_auth,pg_temp -c statement_timeout=5000"},
        )
        self.pool.open()
        try:
            with self.pool.connection() as connection:
                role = connection.execute("""
                    SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb
                            OR pg_has_role(current_user,'iskra_auth_owner','MEMBER')
                            OR has_schema_privilege(current_user,'iskra_auth','CREATE') AS unsafe,
                           pg_has_role(current_user,'iskra_auth_operator','MEMBER') AS operator,
                           pg_has_role(current_user,'iskra_auth_runtime','USAGE') AS runtime,
                           (SELECT max(version) = 3 FROM iskra_auth.schema_version) AS migrated
                      FROM pg_roles WHERE rolname=current_user
                """).fetchone()
                if role["unsafe"] or not role["migrated"] or role["operator"] != operator or role["runtime"] == operator:
                    raise CredentialStoreUnavailable("Incorrect credential database role or migration")
        except (psycopg.Error, PoolTimeout, TooManyRequests, CredentialStoreUnavailable):
            self.close()
            raise CredentialStoreUnavailable("Credential database startup check failed") from None

    def close(self):
        self.pool.close()

    @contextmanager
    def _connection(self, tenant_id=None, lock=False, session_digest=None):
        try:
            with self.pool.connection() as connection:
                if session_digest is not None:
                    row = connection.execute(
                        "SELECT tenant_id FROM iskra_auth.lookup_session(%s)", (session_digest,)
                    ).fetchone()
                    tenant_id = row["tenant_id"] if row else None
                if tenant_id is not None:
                    connection.execute("SELECT set_config('iskra.tenant_id', %s, true)", (tenant_id,))
                    if lock:
                        connection.execute(
                            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (tenant_id,)
                        )
                yield _StatementExecutor(connection)
        except (psycopg.Error, PoolTimeout, TooManyRequests):
            raise CredentialStoreUnavailable("Credential database unavailable") from None
