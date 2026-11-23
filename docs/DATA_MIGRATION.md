# Iskra AI — data migration policy

## Current state

The live legacy graph remains `wiedza.json`; the `KnowledgeGraphStore` protocol is an interface contract and does not silently switch the production Flask graph path.

The tenant-scoped SQLite graph adapter is a tested prototype but is not wired into the legacy Flask graph path. A PostgreSQL graph adapter and internal PostgreSQL document repository exist, with SQL migrations v1/v2, tenant-scoped queries and FORCE RLS; CI tests them against an ephemeral PostgreSQL service using a restricted runtime role. PostgreSQL remains opt-in. No production database, live cutover, durable hosted volume or staging restore/rollback drill has been verified.

This integrated draft combines strict SQLite migration validation and verified tenant-database backup restore. It is not part of the canonical base until reviewed and merged. The PostgreSQL identity lifecycle tables proposed in the architecture document are future work.

See [PostgreSQL architecture and migration design](POSTGRESQL_ARCHITECTURE.md) for the target schema, current adapter/RLS status, tenant-isolation rules, transaction policy, import procedure, rollback, and release gates.

## Required migration sequence
1. Stop writes to the application and confirm the autonomous loop is disabled.
2. Make a byte-for-byte backup of `wiedza.json` and its timestamp; retain the backup outside the application container.
3. Parse the source and validate the complete SQLite database with `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; reject malformed records, non-finite or out-of-range values, dangling edges, and duplicate edges. Migration validation must never clamp, truncate, or silently deduplicate source data.
4. Validate every neuron ID, label, weight, timestamp, and every synapse endpoint.
5. Import into a temporary database transaction; verify row counts and graph invariants.
6. Compare source and destination snapshots semantically, including all twelve foundational pillars.
7. Run read-only smoke tests against the migrated database.
8. Switch the storage implementation only after all checks pass.
9. Keep the original JSON backup and a documented rollback path until the new backend has been proven in staging.

## Database decision
SQLite is appropriate for local development and isolated tests. PostgreSQL is the target for multi-process and multi-tenant hosting because it provides transactions, constraints, and reliable concurrent writes. Do not use the current JSON file as shared multi-tenant production storage.

## Rollback
If any validation, import, or staging smoke test fails, keep the previous deployment and restore the original JSON snapshot. Never overwrite the source file during migration.

## SQLite tenant migration preflight

The SQLite-to-PostgreSQL importer creates a consistent online backup before reading it. It then runs SQLite integrity and foreign-key checks, enumerates tenant IDs across both graph tables, and applies strict migration-specific validation. Any corrupt database, orphaned relationship, invalid numeric value, or duplicate edge stops the run before PostgreSQL writes. The general runtime graph validator may normalize input for application use; it must not be used as the sole migration validator because migration must preserve source data exactly or fail.

## Restore verified SQLite backup

A restore must target a **new file path**. The restore helper verifies the supplied SHA-256 checksum, opens the backup read-only, runs SQLite integrity and foreign-key checks, and confirms the tenant graph schema before publishing the restored file. It writes a private temporary file in the destination directory, flushes it, then publishes it atomically without replacing an existing path. Existing targets are rejected; operators must choose a new destination and handle any application cutover separately.

Example from Python:

```python
from scripts.migrate_tenant_sqlite_to_postgres import (
    restore_private_backup,
    sha256_file,
)

backup = "/secure/backups/iskra-tenant-snapshot.sqlite3"
target = "/secure/restore/iskra-tenants-restored.sqlite3"
expected_sha256 = "copy-the-64-character-checksum-from-the-reviewed-manifest"

result = restore_private_backup(backup, target, expected_sha256)
print(result)
```

A successful file restore is not the same as a production recovery test. Before changing application configuration, validate tenant counts and graph snapshots, confirm the restored file is on durable storage, and test application access in an isolated staging environment. This helper restores only the tenant graph SQLite database; it does not restore legacy JSON state, credentials, uploaded source documents outside this database, or PostgreSQL.


## Staging execution and DSN safety

For the full preflight, separate database identities, staging acceptance tests and rollback procedure, follow [PostgreSQL staging runbook](POSTGRES_STAGING_RUNBOOK.md). The migration CLI resolves the target in this order: explicit --postgres-dsn, ISKRA_POSTGRES_MIGRATION_DSN, then ISKRA_POSTGRES_DSN. It intentionally does not guess from generic DATABASE_URL, which may point to an unrelated service database. Use a dedicated migration credential with NOSUPERUSER NOBYPASSRLS, no table ownership and only the required graph-table DML grants.
