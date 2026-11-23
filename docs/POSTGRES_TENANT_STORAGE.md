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

## Deployment and migration status

This is a tested adapter and schema prototype, not a live migration of Iskra's current JSON graph. The Flask API still uses the existing graph service. Do not set a production PostgreSQL DSN or route customer traffic to this adapter until:
- a backup and repeatable migration/rollback procedure exists;
- a staging database has been migrated and restore-tested;
- runtime credentials are stored outside source control;
- the runtime role is verified as non-superuser and non-BYPASSRLS;
- cross-tenant read/write/delete and missing-context tests pass against the production-like database;
- application services are wired to derive tenant scope only from the authenticated Principal.

CI starts an ephemeral PostgreSQL 16 service, applies the migration as an admin role, creates a separate non-superuser/non-BYPASSRLS runtime role, and runs real database RLS integration tests using that runtime role.
