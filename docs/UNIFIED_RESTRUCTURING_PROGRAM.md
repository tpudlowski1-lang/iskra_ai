# Iskra AI — Unified Restructuring Program

**Status:** active integration program  
**Canonical integration branch:** `refactor/modular-core`  
**Current reviews:** draft PR #4 (modular core) and draft PR #28 (security and tenant storage); do not merge automatically  
**Architecture:** modular Flask monolith  
**Last inventory:** 2026-11-23

## 1. Mission

Bring the existing Iskra AI development streams into one coherent, testable codebase and one release process. Preserve the existing Polish knowledge graph, all twelve foundational pillars, provider fallback behavior, the Dekalog-oriented identity, and the working Flask/Render contract.

This document is the single source of truth for sequencing, ownership boundaries, integration gates, and the status of work that previously lived on separate branches. A branch is not considered integrated merely because it exists or contains passing tests.

## 2. Non-negotiable constraints

- Keep `main` unchanged until a separately approved merge.
- Keep the modular Flask monolith; do not migrate to microservices or FastAPI as part of this program.
- Preserve `app.py` as the compatibility entry point until a tested replacement is proven.
- Preserve `/`, `/api/network`, `/health`, JSON import/export compatibility, and all twelve foundational graph pillars.
- Never trust a tenant ID supplied by a request body, query parameter, URL, or model output. Resolve tenant identity only from verified server-side credentials/session context.
- Do not expose customer documents or tenant APIs until authentication, authorization, storage scoping, and negative cross-tenant tests all pass.
- Keep autonomous work disabled in web workers. Use a separately managed worker with a database-backed lease before enabling scheduled work.
- Never commit secrets, live API keys, personal data, or customer documents.
- Use test-first changes for behavior and security fixes. Do not claim tests pass without fresh CI evidence.
- Prefer low-cost, single-deployment infrastructure. PostgreSQL is the production target for concurrent and multi-tenant use; SQLite remains useful for isolated tests and single-instance development.

## 3. Existing development streams and integration decisions

The following branches were found during the repository inventory:

| Branch | Existing contribution | Integration decision |
|---|---|---|
| `refactor/modular-core` | Modular packages, compatibility façade, SQLite graph adapter, baseline security, tests and readiness docs | Canonical integration branch |
| `iskra-unified-core` | Current upstream graph hardening and regression history | Track and selectively port new fixes; one newer stale-read regression is already covered by an equivalent blueprint-level test on the canonical branch |
| `commercial-mvp` | Product direction, provider configuration, shared-token security middleware prototype, stress tests and deployment notes | Reuse audited ideas and tests; do not merge its older monolithic `app.py` over the modular façade |
| `iskra-api-security` | Shared-token security prototype and related tests | Existing middleware is already present in the canonical branch; audit and extend it for named principals, roles and tenant policy |
| `iskra-sqlite-migration` | Older SQLite persistence implementation and tests | Do not replace the current storage boundary wholesale; compare behavior and port missing regression cases |
| `iskra-tenant-rag` | Tenant API-key prototype, SQLite document/chunk store, FTS retrieval, PDF/DOCX/TXT ingestion | Treat as experimental reference only; security review and modular redesign required before integration |
| `iskra-full-quality-gates` | Earlier CI work | Superseded by the current quality workflow; preserve useful checks, avoid duplicate pipelines |
| `iskra-multithread-stress` | Earlier concurrency suite | Superseded by current stress tests; retain unique tests only |
| `iskra-unified-integrated` | Earlier combined prototype | Historical reference; do not blindly merge stale monolithic files |

The branches have diverged from the current modular branch. Integration must be selective and behavior-based, not a bulk merge. In particular, older branches contain monolithic versions of `app.py` that would undo the modular structure if copied over.

## 4. Target architecture

```text
Flask compatibility entry point (app.py / WSGI)
  ├── configuration and feature flags
  ├── authentication and request-scoped identity
  ├── API blueprints and authorization policies
  ├── domain services
  │    ├── 12-pillar knowledge graph
  │    ├── document ingestion and retrieval
  │    ├── LLM provider router
  │    └── autonomous task orchestration
  ├── storage interfaces
  │    ├── JSON compatibility/import-export
  │    ├── SQLite test/development adapter
  │    └── PostgreSQL production adapter
  ├── security, audit events and redaction
  └── observability and health/readiness checks
```

All domain modules depend on interfaces, not Flask globals. HTTP handlers authenticate first, resolve a trusted principal, authorize the operation, then call a domain service. Storage queries receive tenant scope from that trusted principal and enforce it again in SQL constraints/queries.

## 5. Coordinated workstreams

These streams can be investigated in parallel, but code is integrated in dependency order.

### Stream A — Baseline and compatibility
- Synchronize the canonical branch with the latest upstream regression fixes.
- Confirm imports, WSGI startup, environment validation, route contracts, and twelve pillars.
- Preserve legacy JSON snapshots and rollback behavior.
- Exit gate: complete deterministic suite and compatibility smoke tests pass.

### Stream B — Security and identity
- Retain the existing fail-closed shared `API_TOKEN` WSGI gate as the initial administrator boundary.
- Principal, allowed roles, server-derived tenant context and deny-by-default route policies are implemented.
- The shared `API_TOKEN` remains the compatibility system administrator credential; hashed static credentials and an opt-in SQLite credential registry support tenant principals, expiry and revocation.
- WSGI resolves identity only from verified credentials. Tenant API routes pass the complete Principal into the tenant store factory; client tenant IDs are ignored.
- Tests cover missing/invalid credentials, role boundaries, tenant spoofing, cross-tenant reads/writes, expiry, revocation and backend failure.
- Remaining: user provisioning/account lifecycle, controlled token issuance/rotation, audit events and operational secret management.
- Exit gate for production identity is still open until those lifecycle and operational controls are completed.

### Stream C — Persistence and migration
- Keep the existing JSON format as an import/export compatibility format.
- Keep the current SQLite adapter for tests; audit the older SQLite graph-snapshot prototype separately.
- PostgreSQL graph schema v1, composite tenant keys, foreign keys and RLS ENABLE + FORCE migration are implemented.
- `PostgresGraphStore` derives scope from Principal and sets a transaction-local tenant context; CI verifies it against PostgreSQL 16 with a separate NOSUPERUSER/NOBYPASSRLS runtime role.
- Live tenant API currently uses the tenant-scoped SQLite adapter; the legacy global graph remains JSON. PostgreSQL is not yet wired into the live app.
- Remaining: production migration tooling, dry-run import, byte-for-byte backup, semantic graph comparison, JSON-to-PostgreSQL cutover, rollback and restore drills.
- Exit gate: production migration, isolation, concurrency, restore and rollback tests pass in staging.

### Stream D — Documents and retrieval
- Rebuild the tenant document prototype behind modular service/repository interfaces.
- Enforce upload size, file type, decompression/page/text limits, safe parsing, malware scanning strategy, and private storage.
- Store document ownership and chunk ownership with composite tenant constraints.
- Apply tenant filters to every retrieval query; test adversarial cross-tenant searches.
- Add retrieval quality fixtures and source attribution before model answer generation.
- Exit gate: all tenant-isolation and retrieval-grounding tests pass. No customer document upload before this gate.

### Stream E — LLM router and assistant behavior
- Preserve provider fallback order and JSON schema validation.
- Add bounded timeouts/retries, normalized provider errors, circuit breakers, and structured provider selection telemetry.
- Keep secrets outside logs and responses; redact prompts and sensitive data.
- Add a fixed Polish evaluation corpus for factuality, instruction hierarchy, safe refusals, grounding, and regression behavior.
- Exit gate: deterministic provider tests and versioned quality evaluations pass.

### Stream F — Concurrency and autonomous work
- Retain thread and multi-process stress coverage.
- Use transactional database writes; do not treat process-local locks as distributed coordination.
- Move autonomous work out of Gunicorn workers into a dedicated worker/scheduler.
- Add lease/heartbeat, idempotency, bounded retries, cancellation, and safe shutdown.
- Exit gate: parallel load, worker restart, duplicate-job, and lease-expiry tests pass.

### Stream G — Operations and commercial readiness
- Add structured logs, metrics, traces, health vs readiness checks, audit trail, dependency/security scans, and backup/restore drills.
- Add rate limits and per-tenant/provider budgets after identity is stable.
- Billing and paid onboarding are last, after data protection and service reliability.
- Exit gate: staging smoke tests, recovery drill, security review, and documented cost envelope pass.

## 6. Integration order and dependencies

1. Baseline synchronization and compatibility.
2. Authentication, request principal, and authorization policy.
3. PostgreSQL schema and migration tooling.
4. Tenant-safe domain services and document ingestion.
5. Retrieval and LLM grounding/evaluation.
6. Dedicated worker and concurrency guarantees.
7. Observability, operational recovery, rate limits and budgets.
8. Billing/commercial onboarding.

Streams A, E (provider audit only), F (test inventory only), and G (observability design only) can be investigated concurrently. Production code that depends on identity or storage must wait for those foundations. No workstream may bypass the integration gates.

## 7. One CI/release gate

Every integration commit must run:
- Python compile/import checks;
- deterministic unit and API contract tests;
- security and authorization tests;
- storage and migration tests;
- thread and multi-process stress tests;
- dependency/security scanning;
- staging smoke tests before release.

A passing unit suite is not a production-readiness claim. The release record must list exact workflow URLs, commit SHA, Python versions, test counts, skipped tests, and any remaining blockers.

## 8. Implementation snapshot — 2026-11-23

The following is implemented in the current review chain (PR #28) and verified by CI on commit `92ebb804404f5157c4567d7fd37ad2fde515ce4d`:

- Request principal and role policy; server-side credential resolution.
- Optional persistent SQLite credential registry with digest-only token storage, expiry and revocation.
- Tenant API backed by principal-bound SQLite graph storage, with atomic initialization of the twelve foundational pillars.
- PostgreSQL graph schema and adapter prototype with RLS policies, tested on PostgreSQL 16.
- Python 3.11 and 3.12: 104 tests each; compileall and pip-audit passed.

This does not mean the PostgreSQL backend is live or the application is production-ready. The current live tenant API uses SQLite; the legacy global graph remains on JSON. PostgreSQL migration/cutover, backup/restore, account provisioning, audit events and staging operations remain outstanding.

## 9. Current blockers — do not mark production-ready

- Shared API-token authentication exists at the WSGI boundary, but named user lifecycle, roles, and request-scoped tenant authorization are not implemented.
- The current SQLite adapter is not wired into the live Flask application.
- PostgreSQL persistence and migrations are not implemented.
- The tenant document/RAG prototype is not integrated and has not passed a full security review.
- Dedicated worker leases, observability, staging verification, and restore drills remain outstanding.
- Billing and paid customer onboarding are out of scope until the preceding controls pass.

## 10. Definition of done

The restructuring program is complete only when:
1. One canonical modular codebase contains the reviewed contributions from the historical branches.
2. Existing API and graph compatibility tests pass.
3. Authentication and tenant authorization are enforced server-side and pass negative tests.
4. PostgreSQL migrations and JSON import/rollback are proven in staging.
5. Document retrieval cannot cross tenant boundaries and produces traceable sources.
6. Provider fallback and assistant behavior pass deterministic and quality evaluations.
7. Autonomous jobs cannot run duplicated across web workers.
8. CI, security scans, backup/restore, and staging checks are green on the exact release commit.
9. Documentation accurately distinguishes implemented, experimental, and unavailable features.

Until then, the application remains an experimental system under controlled development, not a production multi-tenant SaaS.
