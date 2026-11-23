# Iskra AI — data migration policy

## Current state
The existing graph is stored in `wiedza.json`. The extracted `SiecNeuronowa` keeps this format for compatibility. The new `KnowledgeGraphStore` protocol is an interface contract only; it does not silently change the production backend.

## Required migration sequence
1. Stop writes to the application and confirm the autonomous loop is disabled.
2. Make a byte-for-byte backup of `wiedza.json` and its timestamp; retain the backup outside the application container.
3. Parse the source JSON and validate that it contains `neurons` and `synapses`.
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


## Staging execution and DSN safety

For the full preflight, separate database identities, role checks, staging acceptance tests and rollback procedure, follow [PostgreSQL staging runbook](POSTGRES_STAGING_RUNBOOK.md). The migration CLI resolves the destination from explicit `--postgres-dsn`, then `ISKRA_POSTGRES_MIGRATION_DSN`, then `ISKRA_POSTGRES_DSN`. It intentionally does not guess from generic `DATABASE_URL`, which may point to an unrelated service database. Use a dedicated migration credential with `NOSUPERUSER NOBYPASSRLS`, no table ownership and only the required graph-table DML grants.
