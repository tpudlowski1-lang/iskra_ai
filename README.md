# Iskra AI — Unified Core

Iskra AI is an experimental Polish-language knowledge-system project implemented as a modular Flask monolith. It preserves the twelve foundational pillars and the legacy graph model while adding tenant-scoped storage adapters, verified credential handling and provider routing.

## Project status

**Development / integrated release candidate — not production-ready and not ready for sale.** The repository contains working modules and PostgreSQL integration tests, but no verified production database cutover, durable customer hosting, public account lifecycle, complete observability/incident response, or commercial/legal clearance.

The canonical integration branch is `refactor/modular-core`. Historical branches are reference material; changes are ported selectively after review. See:
- [Unified restructuring program](docs/UNIFIED_RESTRUCTURING_PROGRAM.md)
- [Production readiness checklist](docs/PRODUCTION_READINESS.md)
- [Commercial readiness gate](docs/COMMERCIAL_READINESS.md)
- [Data migration policy](docs/DATA_MIGRATION.md)
- [Tenant knowledge chat API](docs/KNOWLEDGE_CHAT_API.md)
- [LLM provider allowlist policy](docs/LLM_PROVIDER_ALLOWLIST.md)
- [LLM provider data handling](docs/LLM_PROVIDER_DATA_HANDLING.md)
- [Autonomous worker data minimization](docs/AUTONOMOUS_WORKER_DATA_MINIMIZATION.md)
- [Dependency/license inventory](docs/DEPENDENCY_LICENSE_AUDIT.md)

## Application entry points and authentication

- `app.py` — Flask compatibility application and legacy global graph dashboard.
- `wsgi.py` — WSGI entry point with fail-closed authentication middleware.
- `/health` — public hosting health probe.
- `/` and `/api/network` — protected legacy global graph dashboard/API.

The shared system `API_TOKEN` protects the legacy application routes. The security modules also implement hashed tenant credential storage, expiry/revocation and operator issue/rotate/revoke commands. Verified tenant principals are derived from credentials on the server; tenant scope must never come from request input.

This is **not yet a complete customer account product**: self-service signup, account recovery, customer-managed credential lifecycle, billing and a complete tenant administration UI are not finished. Use `wsgi:app` for public WSGI deployment; do not expose `app:app` directly because that bypasses the WSGI authentication wrapper on the canonical base branch.

## Architecture

- `iskra/config.py` — validated runtime configuration.
- `iskra/knowledge/graph.py` — legacy global graph, twelve pillars and JSON persistence.
- `iskra/llm/router.py` — OpenAI-compatible, DeepSeek and Gemini routing with JSON-object validation and fallback.
- `iskra/llm/tenant_policy.py` — draft per-tenant provider allowlist, intersected with the deployment-wide allowlist.
- `iskra/llm/data_minimization.py` — draft best-effort outbound redaction for common secrets and identifiers; not a full DLP solution.
- `iskra/api/routes.py` — protected API blueprint and tenant graph operations.
- `iskra/security/` — principal, policy, credential and SQLite credential registry modules.
- `iskra/storage/sqlite.py` — tenant-scoped transactional SQLite graph adapter.
- `iskra/storage/postgres.py` — optional PostgreSQL tenant graph adapter with row-level security.
- `iskra/documents/` — internal tenant document service, bounded PDF/DOCX/TXT parsers, SQLite/FTS5 and optional PostgreSQL repository.

## Data and tenant storage

There are two separate storage paths:

1. **Legacy global knowledge graph:** remains in `$DATA_DIR/wiedza.json`; it is not yet migrated to PostgreSQL. Writes use atomic replacement and a POSIX file lock. This is not a distributed multi-instance store.
2. **Tenant graph storage:** the API uses a principal-bound SQLite store by default. PostgreSQL is an implemented opt-in adapter with migrations and row-level security (RLS ENABLE + FORCE). CI runs integration tests against PostgreSQL 16 using a separate `NOSUPERUSER NOBYPASSRLS` runtime role. PostgreSQL is not automatically provisioned or selected in production.

The tenant migration utility is dry-run-first and supports an explicit transactional apply. It resolves the destination only from an explicit CLI DSN or the dedicated migration/runtime DSN variables; it never guesses from generic DATABASE_URL. No production cutover, restore rehearsal or rollback drill has been completed.

Tenant SQLite graph and document stores validate every path component, reject symlinked ancestors, create private directories/files (0700/0600), and use O_NOFOLLOW where available. These checks reduce path attacks but do not eliminate TOCTOU races against a process able to mutate ancestor directories.

## Documents and RAG status

An internal tenant document service supports bounded PDF, DOCX and TXT parsing, tenant-scoped SQLite/FTS5 storage, and an optional PostgreSQL repository with tenant RLS. Its parser runs in a resource-limited child process and validates the returned JSON payload.

**No document HTTP routes are registered, customer uploads are disabled, and no RAG answer generation is connected.** The parser worker clears inherited environment variables before parsing, applies a restrictive umask and file-descriptor limit, but is not a full OS/container sandbox: it runs under the same OS user and has no seccomp or network namespace policy. Do not upload customer documents or enable this service until a dedicated low-privilege no-network sandbox, malware quarantine, retention, audit, quotas and restore controls are reviewed and tested.

## LLM providers

Configure credentials only in hosting secrets/environment settings; never commit API keys. External providers are deny-by-default: without `LLM_ALLOWED_PROVIDERS`, the router makes no outbound LLM calls. Primary and fallback providers are checked against the same deployment-level allowlist.

- `LLM_ALLOWED_PROVIDERS`: explicit comma-separated allowlist (for example `deepseek,openai`); empty/unset disables all external providers.
- `LLM_PROVIDER`: `openai`, `deepseek`, or `gemini`.
- `LLM_FALLBACK_PROVIDERS`: comma-separated fallback order.
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`).
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default `deepseek-chat`).
- `GEMINI_API_KEY`, `GEMINI_MODEL` (both required to enable Gemini).

Live provider calls require customer-owned API credentials and separate cost, privacy and provider-terms review. The Render manifest leaves the allowlist empty and autoDeploy disabled until an operator explicitly approves provider processing and deployment. The optional autonomous worker uses only a fixed public taxonomy rather than the mutable global graph, but ordinary user prompts are not automatically redacted. CI tests validate deterministic routing behavior; they do not prove live provider availability or legal compliance.

## Deployment and operations

The supplied Render manifest is a deployment template, not proof of a live deployment. It uses one Gunicorn worker because the legacy global JSON graph is not a shared transactional multi-instance store. Render autoDeploy is disabled and external provider allowlist is empty by default; both require explicit operator action. It does not provision a persistent disk or managed PostgreSQL database. The default `DATA_DIR` may therefore be ephemeral on a hosted platform; data can be lost on restart/redeploy.

Before a production deployment: attach and verify durable storage or configure a managed database, run migration/restore/rollback drills using the [PostgreSQL staging runbook](docs/POSTGRES_STAGING_RUNBOOK.md), configure secrets and TLS, add monitoring/alerting and incident response, and perform staging smoke tests. Keep `ENABLE_AUTONOMOUS_LOOP=false` on web deployments; a dedicated singleton worker with coordination and safe shutdown is still required.

## Development and tests

```bash
python -m pip install -r requirements.txt
python -m compileall -q app.py wsgi.py security.py iskra tests
python -m unittest discover -s tests -p "test_*.py" -v
```

GitHub Actions runs the full test suite on Python 3.11 and 3.12, including PostgreSQL 16 integration tests, plus dependency vulnerability auditing.

## Not production-ready as a paid multi-tenant SaaS

Implemented tenant adapters and green CI do not equal a production SaaS. Remaining gates include public account lifecycle, staging PostgreSQL cutover, durable backups and restore, independent security review, parser sandboxing, malware scanning, retrieval evaluation and provenance, tenant quotas, CSRF protection for browser mutations, monitoring/alerting, incident response, license/IP review, privacy/contracts, cost model, onboarding, support and validated product scope. See [Commercial readiness gate](docs/COMMERCIAL_READINESS.md).

## Tenant knowledge chat API (draft feature)

The current feature branch adds an authenticated POST /api/tenant/chat endpoint. It searches only documents belonging to the authenticated Principal, sends at most five bounded excerpts to the configured LLM, and requires exact server-resolved citations. No source means no provider call. Tenant document list/search/delete routes are also available; upload is admin-only and disabled by default through ISKRA_ENABLE_DOCUMENT_INGESTION=false. A minimal responsive chat UI is available at /assistant; it accepts an API token for the current page session only and does not persist it or maintain server-side chat history. See docs/KNOWLEDGE_CHAT_API.md.
