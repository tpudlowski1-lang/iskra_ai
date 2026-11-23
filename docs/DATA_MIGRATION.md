# Iskra AI — data migration policy

## Current state

The existing live graph is stored in `wiedza.json`. The extracted `SiecNeuronowa` keeps this format for compatibility. The `KnowledgeGraphStore` protocol is currently an interface contract; it does not silently change the production backend.

The tenant-scoped SQLite graph adapter is a tested development/migration component, not the production multi-tenant backend. PostgreSQL is the target for multi-process and multi-tenant hosting. No PostgreSQL adapter or production cutover is implemented yet.

See [PostgreSQL architecture and migration design](POSTGRESQL_ARCHITECTURE.md) for the proposed schema, tenant-isolation rules, transaction policy, import procedure, rollback, and release gates. That document is a design proposal, not a claim that PostgreSQL is already available.

## Required migration sequence

1. Stop writes to the application and confirm the autonomous loop is disabled.
2. Make a byte-for-byte backup of the source and its timestamp; retain the backup outside the application container.
3. Record the source size and SHA-256 fingerprint and verify the backup is readable.
4. Parse the entire source and validate every neuron ID, label, weight, timestamp, and synapse endpoint. Reject invalid data rather than silently discarding or coercing it.
5. Run a dry-run import and report counts and validation errors without writing destination data.
6. Import into a destination transaction; verify row counts, constraints, referential integrity, and graph invariants.
7. Compare source and destination snapshots semantically, including all twelve foundational pillars and their required links.
8. Run read-only service/API smoke tests against the destination.
9. Switch storage only behind an explicit feature flag, after a final backup and a staging rehearsal.
10. Keep the original source backup immutable and retain a tested rollback path until the new backend is proven.

Migration must be idempotent and keyed by source fingerprint, tenant mapping, and schema version. A repeated completed import must not duplicate rows or overwrite newer data silently. Migration must never run automatically during web application startup.

## Tenant mapping and trust

Tenant scope must come from verified server-side identity. Never infer it from a request body, URL, query parameter, model output, or uploaded document.

The legacy JSON graph represents one graph. Import it into one explicitly selected tenant; do not split it across tenants or infer historical ownership. Existing SQLite tenant IDs may be retained only when they are linked to a trusted tenant registry; otherwise require an explicit operator-reviewed mapping.

## Rollback

If validation, import, or staging smoke tests fail, keep the previous deployment and restore the original source snapshot. Never overwrite the source file during migration. If a cutover has started, stop writes first, switch the feature flag back, restore the verified artifact if necessary, and confirm semantic equality before reopening traffic.

## Database decision

SQLite remains appropriate for local development and isolated tests. PostgreSQL is the target for concurrent and multi-tenant hosting. Do not use the current JSON file as shared multi-tenant production storage. Do not select a paid hosting vendor or enable production PostgreSQL until authentication, tenant isolation, migration, restore, and cost gates are satisfied.
