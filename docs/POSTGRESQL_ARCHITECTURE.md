# Iskra AI — PostgreSQL architecture and migration design

**Status:** design proposal and implementation-state record; not production cutover  
**Base:** `refactor/modular-core`  
**Scope:** durable graph persistence, tenant isolation, migration from legacy JSON and the current SQLite prototype.

## 1. Decision summary

## Implementation status snapshot — 2026-11-23

The repository now contains a tested PostgreSQL prototype; this document must not be read as saying that the adapter or RLS do not exist. The distinction is between code/CI evidence and a verified production cutover.

Implemented on the canonical modular-core baseline:

- `iskra/storage/postgres.py`: `PostgresGraphStore` requires a verified `Principal`, rejects the system principal as a customer tenant, derives the tenant ID from the principal, uses transaction-local `set_config('iskra.tenant_id', ..., true)`, and includes explicit tenant predicates.
- `iskra/documents/postgres_repository.py`: internal `PostgresDocumentRepository` binds each operation to a verified principal and applies the same transaction-local tenant scope. The document service has no public HTTP routes and does not generate RAG answers.
- `migrations/0001_tenant_graph.sql` and `0002_tenant_documents.sql`: graph and document/chunk tables, composite tenant keys/foreign keys, `iskra_schema_migrations(version, applied_at)`, and ENABLE/FORCE RLS policies.
- CI applies both migrations to ephemeral PostgreSQL 16 and tests graph/document isolation using a separate `NOSUPERUSER NOBYPASSRLS` runtime role.
- `SQLiteGraphStore` has tenant-bound operations and atomic `load_or_initialize()`, but its validator intentionally normalizes/clamps application input and the adapter is not wired into the legacy Flask graph path.
- `SQLiteCredentialStore` and an operator credential CLI exist. WSGI authentication and direct development-entrypoint regression coverage are being hardened in draft PRs #50/#51.
- The baseline includes a dry-run-first SQLite-to-PostgreSQL migration utility. Strict lossless migration validation and verified backup restore are proposed together in draft PR #59; that draft is not part of the canonical baseline until reviewed and merged.

Not implemented/verified:

- No live PostgreSQL deployment, production cutover, persistent hosted database, migration/restore/rollback drill, or customer traffic.
- No PostgreSQL tenant/user/membership/credential lifecycle tables; the identity schema below remains a future design proposal.
- No general checksum-verified schema migration runner or production migration orchestration is attested. The SQL migration files and version table are present, but production operator procedures remain a release gate.
- No public document upload routes, production object storage, RAG generation, or full parser OS/container sandbox.

For operational facts about the current adapter and database role, also see [PostgreSQL tenant storage](POSTGRES_TENANT_STORAGE.md). For current migration and recovery implementation, check the GitHub PR and CI evidence rather than assuming a draft is part of the base branch.


PostgreSQL is the target durable backend for a multi-process deployment. The current JSON graph remains a compatibility/import-export format. The current `SQLiteGraphStore` remains useful for local development and isolated tests; it is not promoted to the production multi-tenant backend.

This document does not enable PostgreSQL, change the live Flask storage path, create cloud resources, or authorize customer data ingestion. Implementation starts only after the authentication/principal contract and storage service boundary are stable, and after negative cross-tenant tests are available.

The application remains a modular Flask monolith. No microservice split is proposed.

## 2. Current-state findings

The inspected canonical branch currently has:

- `wiedza.json` as the live graph snapshot, loaded and written by `SiecNeuronowa`.
- Atomic JSON replacement, file locking, and a compatibility graph containing twelve foundational pillars.
- A `KnowledgeGraphStore` protocol with only `load()` and `save(graph)`; transaction and tenant-scope semantics are not yet part of the contract.
- A tenant-bound SQLite graph adapter. Its graph tables use composite tenant/node keys and composite foreign keys, and every graph query is scoped to the store's constructor-bound tenant.
- Tenant API routes that obtain `tenant_id` from the authenticated `Principal`, not from the request body. The SQLite first-read initialization must use the separately developed atomic `load_or_initialize()` path before concurrent production use.
- A security design with immutable server-derived principals and a persistent SQLite credential registry. WSGI integration and entrypoint regression coverage remain under review in draft PRs #50/#51.
- A PostgreSQL graph adapter and internal PostgreSQL document repository, with SQL migrations v1/v2, a schema-version table, and FORCE RLS. These are CI-tested prototypes, not a production deployment.
- A dry-run-first SQLite tenant migration utility; strict migration validation and verified restore are being combined in draft PR #59.

The current PostgreSQL schema models graph and document/chunk data only. It does not yet implement the proposed tenant lifecycle, users, memberships, PostgreSQL credentials, audit events, or migration-run ledger. The current schema-version table stores version and applied timestamp; checksum-based schema migration governance remains future work.

## 3. Target runtime flow and trust boundary

1. WSGI authentication validates the credential.
2. Middleware creates an immutable principal from server-managed credential data.
3. Authorization checks the principal's role and permitted operation.
4. The application service receives the principal (or an explicit immutable tenant scope derived from it).
5. A repository transaction applies the tenant scope to every query.
6. PostgreSQL constraints enforce tenant-consistent relationships; optional row-level security adds defense in depth.

**Never** accept tenant identity from a URL, query parameter, request body, uploaded document, LLM response, or caller-controlled header. A tenant identifier in a payload is either rejected or ignored; it never selects storage scope.

A system administrator may have an explicit system-wide service path. Ordinary tenant repositories must require a non-empty tenant scope and must not expose an unscoped graph query.

## 4. Proposed PostgreSQL schema

Use UUID primary keys generated by the application or database. Use `timestamptz` for persisted timestamps and `numeric` or bounded `double precision` for graph weights; the implementation must choose one representation and preserve round-trip semantics.

### Core identity and tenancy

- `tenants(id, slug, display_name, status, created_at, updated_at)`
  - Unique normalized `slug`; status is constrained to known lifecycle values.
- `users(id, email_normalized, display_name, status, created_at, updated_at)`
  - Unique normalized email where accounts are enabled. Account lifecycle is separate from credentials.
- `tenant_memberships(tenant_id, user_id, role, status, created_at, updated_at)`
  - Primary key `(tenant_id, user_id)`; role constrained to the application role set.
- `api_credentials(id, tenant_id, user_id, token_digest, label, expires_at, revoked_at, created_at, last_used_at)`
  - Store only a cryptographic digest of a high-entropy token, never the raw token.
  - Unique `token_digest`; composite foreign key to membership ensures the credential belongs to the same tenant/user.
  - Credential lookup must return a principal only after digest verification and status/expiry/revocation checks.

The precise relationship between machine principals and human users is an implementation decision: service credentials may have a nullable `user_id` but must still be tenant-bound and carry a constrained service identity. Do not overload a shared legacy admin token as a customer account.

### Knowledge graph

- `graph_neurons(tenant_id, node_id, label, weight, created_at, updated_at)`
  - Primary key `(tenant_id, node_id)`.
  - Check constraints for non-empty bounded node IDs, bounded label length, and `weight BETWEEN 0 AND 1`.
- `graph_synapses(tenant_id, source_id, target_id, strength, created_at)`
  - Primary key `(tenant_id, source_id, target_id)`.
  - Composite foreign keys `(tenant_id, source_id)` and `(tenant_id, target_id)` to `graph_neurons`, with deliberate delete behavior.
  - Check constraint `strength BETWEEN 0 AND 1`.
  - Indexes beginning with `tenant_id` for graph traversal and tenant-scoped reads.

The composite keys are essential: a synapse cannot point from one tenant to a node in another tenant even if node IDs collide. Node IDs remain local to a tenant, matching the SQLite prototype.

### Schema and operations

- `schema_migrations(version, checksum, applied_at, execution_ms)`: append-only migration ledger; each migration is immutable once released.
- `migration_runs(id, tenant_id, source_kind, source_fingerprint, status, started_at, completed_at, counts_json, error_code)`: records import attempts without storing source secrets or graph contents in logs.
- `audit_events(id, tenant_id, actor_subject, action, resource_type, resource_id, outcome, occurred_at, request_id, metadata_json)`: append-only, bounded metadata; redact tokens, prompts, and personal data.

Document and RAG tables are intentionally not part of this first persistence milestone. They require a separate threat model, private object-storage design, ingestion limits, and retrieval isolation tests.

## 5. Tenant isolation controls

Required controls:

- Every tenant-owned table has a non-null `tenant_id`.
- Every repository method receives scope from the authenticated principal; do not instantiate a tenant repository from user-supplied identifiers.
- Every SELECT, UPDATE, and DELETE includes tenant scope. Inserts derive `tenant_id` from the repository scope, not from input records.
- Use composite primary/foreign keys for relationships across tenant-owned tables.
- Add automated negative tests proving tenant A cannot read, mutate, delete, enumerate, or infer tenant B records, including guessed IDs and duplicate node IDs.
- Use parameterized SQL exclusively.
- Do not return tenant identifiers or internal database errors in responses unless the API contract explicitly permits them.

PostgreSQL RLS is already enabled and forced by migrations 0001/0002 for the graph and document tables. Policies use the transaction-local `iskra.tenant_id` setting; both adapters set it within each transaction and also use explicit tenant predicates. CI verifies missing-context and cross-tenant read/write behavior with a separate `NOSUPERUSER NOBYPASSRLS` role. Remaining gates are an independent review, connection-pool/reuse testing in the actual hosting topology, and staging verification. RLS is not a replacement for application authorization and does not protect against SQL injection or arbitrary code executing with application DB credentials.

## 6. Storage interface evolution

The baseline already has SQLite and PostgreSQL graph adapters implementing the snapshot-style `load()`/`save()` contract, plus an internal PostgreSQL document repository. The current graph protocol is still minimal; evolve it deliberately before production cutover:

- Keep a graph repository contract for tenant-scoped `load`, `save`, and atomic `load_or_initialize`.
- Define explicit transaction/unit-of-work semantics; do not hide multi-step operations behind unrelated autocommit calls.
- Make tenant scope explicit and immutable for a repository instance, but create it only from a trusted principal in the service layer.
- Define typed domain errors for validation, not-found, conflict, unavailable, and serialization/deadlock retry cases.
- Keep JSON import/export as an adapter/service, not as an alternative live database writer after cutover.
- Keep SQLite and PostgreSQL adapters contract-tested against the same fixtures.

Do not add a fake `transaction()` method to the current protocol until its rollback and nested-call semantics are specified and tested.

## 7. Transaction and concurrency policy

- Use a bounded connection pool with explicit connect, statement, and pool-acquisition timeouts.
- Use short transactions; never hold a database transaction while calling an LLM, parsing a large file, or waiting on network I/O.
- Use PostgreSQL `READ COMMITTED` by default for ordinary graph operations, with explicit row locking or optimistic version checks for conflicting read-modify-write operations.
- Use `SERIALIZABLE` only for workflows that require it and implement bounded retry for serialization failures.
- Use `INSERT ... ON CONFLICT` only where idempotent semantics are defined.
- Make first-tenant initialization atomic: lock/claim tenant initialization, seed the twelve pillars once, and commit as one transaction.
- Add a graph revision/version field if clients need optimistic concurrency. Reject stale writes rather than silently overwriting newer snapshots.
- Do not rely on Python locks, process-local caches, or SQLite file locks for multi-replica coordination.

## 8. Migration sources and canonical mapping

### Legacy JSON

Source: `wiedza.json`, shape `{ "neurons": { ... }, "synapses": [ ... ] }`.

- Import as one explicitly selected tenant (initially the system tenant only unless an operator deliberately provisions another tenant).
- Preserve node IDs, labels, weights, timestamps, and edge endpoints/strengths.
- Preserve all twelve foundational pillars and required foundational links.
- Do not infer ownership or split one legacy graph across tenants.
- Preserve the original file byte-for-byte as a backup; never mutate it during import.

### Existing SQLite prototype

- Inventory database schema, tenant IDs, row counts, constraints, and integrity before importing.
- Map `graph_neurons` and `graph_synapses` to the equivalent PostgreSQL tables.
- Verify foreign-key integrity and duplicate/invalid records before starting a destination transaction.
- Preserve each existing tenant ID only when it is linked to a trusted server-side tenant registry; otherwise stop and require an explicit mapping file reviewed by an operator.
- Do not migrate experimental credentials into the new credential schema without a separate credential security review.

## 9. Safe migration protocol

Migration tooling must support `--dry-run` and an explicit source/target selection. A migration must never run automatically during web application startup.

1. **Preflight:** verify source readability, free disk, target connectivity, schema compatibility, expected tenant mapping, and autonomous worker shutdown.
2. **Backup:** create a byte-for-byte source backup outside the application container; record size, timestamp, and SHA-256 fingerprint. Verify the backup can be read.
3. **Validate:** parse the entire source; reject invalid IDs, malformed records, non-finite numbers, dangling edges, duplicate IDs/edges, and missing required pillars/links. Do not silently clamp or discard invalid migration data.
4. **Dry run:** report counts and validation errors without writing destination data.
5. **Import:** create a migration-run record; import one tenant in a single transaction or bounded, resumable batches with an explicit checkpoint protocol. For a single graph snapshot, prefer one transaction.
6. **Verify:** compare normalized source and destination snapshots, counts, checksums, all twelve pillars, all required links, and referential integrity.
7. **Read-only rehearsal:** run API/service smoke tests against the destination with writes disabled.
8. **Cutover:** stop writes, take a final backup, re-run source fingerprint/count checks, switch the storage configuration flag, restart the service, and verify health/readiness.
9. **Observe:** keep the source backup immutable and monitor errors/latency. Do not dual-write unless a separately designed reconciliation protocol exists.
10. **Rollback:** stop writes, switch the feature flag back to the previous backend, restore the exact pre-cutover artifact if required, and verify the restored graph. Never attempt an improvised reverse migration during an incident.

Idempotency: a source fingerprint plus tenant ID and migration version identifies an import. A repeated completed import must be a no-op or an explicit operator-approved replacement; it must never duplicate graph rows or overwrite newer destination data silently.

## 10. Backup, restore, and retention

- Use PostgreSQL-native consistent backups (for example, `pg_dump` custom format) and test restores into a clean database.
- Encrypt backups at rest and in transit; restrict access to the minimum operator identities.
- Define retention only after the deployment and data classification are chosen; avoid promising a retention period that the hosting plan cannot meet.
- Keep secrets out of backups where practical; credential digests remain sensitive authentication data.
- Perform and record a restore drill before any production cutover and after material schema changes.
- Document recovery point and recovery time objectives only after measuring the actual deployment.

## 11. Test and release gates

No PostgreSQL production cutover until all of the following pass:

### Contract and schema
- Same repository contract suite passes against SQLite and PostgreSQL.
- Migration upgrades from an empty database and from every supported prior schema version.
- Migration checksum mismatch and unsupported downgrade fail safely.
- Constraint tests reject invalid weights, duplicate IDs, dangling edges, and cross-tenant foreign-key references.

### Isolation and authorization
- Missing principal, invalid credential, revoked credential, expired credential, and wrong role are denied.
- Spoofed tenant IDs in body/query/path/header/model output cannot change storage scope.
- Cross-tenant read/write/delete/list/ID-guessing tests all fail closed.
- RLS policies are tested under the actual restricted application DB role and pooled connections.

### Concurrency and recovery
- Concurrent first initialization seeds exactly one foundational graph.
- Concurrent updates do not silently lose writes; stale revisions produce conflicts or deterministic merges.
- Deadlocks and serialization failures have bounded retry and observable terminal errors.
- Failed migration rolls back completely; rerun is idempotent.
- Backup restore reproduces a semantically identical graph and tenant registry.

### Application and operations
- Existing routes and JSON export/import compatibility remain covered.
- WSGI startup uses the authenticated entry point and never enables tenant routes with an unconfigured storage backend.
- No customer document/RAG path is enabled in this milestone.
- Staging smoke test, security review, backup/restore drill, and cost review are documented.

## 12. Cost-conscious deployment constraints

The repository should not bind itself to a paid database vendor in this design phase. First support standard PostgreSQL through a normal connection URL and environment-based configuration. Local development can use a local PostgreSQL container or SQLite tests. A hosted free tier may be evaluated later, but only after checking its current storage, inactivity, backup, connection, and data-retention limits.

Do not commit a hosting provider, paid plan, or production database URL. Never put credentials in GitHub Actions logs or repository files.

## 13. Remaining implementation and release sequence

1. Review the authentication/principal/credential stack (#50/#51) and confirm the exact production WSGI entrypoint and durable credential-store configuration.
2. Review the existing graph/document adapters, migrations 0001/0002, FORCE RLS policies, and runtime-role grants; complete an independent tenant-isolation review.
3. Review the combined strict migration/verified restore work in draft PR #59; resolve any remaining migration, checksum, semantic-readback, and rollback gaps.
4. Provision an isolated staging PostgreSQL database with a restricted runtime role; apply migrations, migrate representative synthetic data, verify semantic equality, and rehearse restore/rollback.
5. Add and test a real schema migration workflow with immutable checksums and controlled upgrade/rollback semantics before schema changes become operationally routine.
6. Keep the global JSON graph and document/RAG service paths disabled for customers until service wiring, parser sandbox, object storage, retrieval isolation, privacy and operational gates pass.
7. Perform production cutover only after staging evidence, operational ownership, cost review, and a separate explicit release decision.

## 14. Explicit non-goals

This design does not create the proposed PostgreSQL customer-account/membership/credential lifecycle, enable public self-service token issuance, enable customer uploads, enable RAG, configure a hosted database, wire the PostgreSQL graph into the legacy live Flask graph path, migrate live data, or merge any existing draft PR. The legacy JSON graph remains the live backend until a separately reviewed service integration and production cutover are complete.
