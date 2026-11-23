# PostgreSQL tenant graph storage

## Design

`PostgresGraphStore` implements the graph snapshot contract using Psycopg 3. Each instance requires a verified `Principal`; it derives the tenant ID from that principal and rejects the global `system` principal.

Every database operation:
1. opens a database connection;
2. starts a transaction;
3. sets `iskra.tenant_id` using transaction-local `set_config(..., true)`;
4. reads or writes only the bound tenant;
5. commits or rolls back and closes the connection.

The migration `migrations/0001_tenant_graph.sql` creates tenant-keyed graph tables, composite foreign keys, and PostgreSQL row-level security (RLS) policies with both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Missing tenant context returns no rows and rejects writes. The application query also includes explicit tenant predicates as defense in depth.

## Database role requirements

Do not run the web application as the PostgreSQL migration owner, a superuser, or a role with `BYPASSRLS`. Use a dedicated runtime role with `NOSUPERUSER NOBYPASSRLS`, and grant only the required table permissions.

Example operator sequence (replace the placeholder secret using a secret manager; never commit it):

```sql
CREATE ROLE iskra_app LOGIN PASSWORD '<managed-secret>' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE iskra TO iskra_app;
GRANT USAGE ON SCHEMA public TO iskra_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON iskra_graph_neurons, iskra_graph_synapses TO iskra_app;
```

Apply the migration with a separate schema-owner/migration identity before deploying application code. The application runtime role should not own the tables and must not have `BYPASSRLS`.

The custom transaction-local setting is a defense against accidental unscoped queries and application-layer tenant mistakes. It is not a substitute for preventing SQL injection or for protecting against arbitrary malicious code running with the application's database credentials.

## SQLite tenant database migration

The operator utility `python -m scripts.migrate_tenant_sqlite_to_postgres` is dry-run-first:

- creates a consistent SQLite backup using the online backup API;
- writes the backup and manifest with private filesystem permissions (directory 0700, files 0600);
- records a SHA-256 checksum without including the PostgreSQL DSN or secrets;
- validates every source tenant graph before connecting to PostgreSQL;
- reports tenant and graph counts without changing PostgreSQL by default;
- requires explicit `--apply` to write;
- refuses to overwrite any target tenant unless `--replace-existing` is also explicitly supplied;
- migrates every tenant in one PostgreSQL transaction and verifies semantic read-back before commit, so an error rolls back the entire migration.

Example dry run:

```bash
python -m scripts.migrate_tenant_sqlite_to_postgres \
  --source /path/to/iskra_tenants.sqlite3 \
  --backup-dir /secure/iskra-backups
```

Only after reviewing the backup, checksum, report, target role and restore plan should an operator add `--apply` and a secret-managed `--postgres-dsn`. Use `--replace-existing` only for a deliberately approved overwrite. This utility migrates the tenant SQLite graph database; it does not migrate the separate legacy global JSON graph.

## Deployment and migration status

The Flask tenant API can select SQLite (default) or PostgreSQL through validated server-side settings. PostgreSQL remains opt-in and is not the default. Set `ISKRA_TENANT_STORAGE_BACKEND=postgres` and `ISKRA_POSTGRES_DSN` only after applying the migration with a separate operator role and completing staging checks. The legacy global graph remains JSON. Do not route production customer traffic to PostgreSQL until:
- a backup and repeatable migration/rollback procedure exists;
- a staging database has been migrated and restore-tested;
- runtime credentials are stored outside source control;
- the runtime role is verified as non-superuser and non-BYPASSRLS;
- cross-tenant read/write/delete and missing-context tests pass against the production-like database;
- application services are wired to derive tenant scope only from the authenticated Principal; the runtime factory now enforces this selection.

CI starts an ephemeral PostgreSQL 16 service, applies the migration as an admin role, creates a separate non-superuser/non-BYPASSRLS runtime role, and runs real database RLS integration tests using that runtime role.
