# Iskra AI — data migration policy

## Current state
The existing graph is stored in `wiedza.json`. The extracted `SiecNeuronowa` keeps this format for compatibility. The new `KnowledgeGraphStore` protocol is an interface contract only; it does not silently change the production backend.

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
