# Iskra AI — production readiness

This checklist is intentionally conservative. Passing CI does not by itself make Iskra a production-ready multi-tenant SaaS.

## Current verified baseline
- [x] Existing Flask compatibility routes and twelve foundational graph pillars retained.
- [x] Modular configuration, knowledge graph, LLM router, API, security headers and autonomous worker boundaries.
- [x] Dashboard renders graph labels with DOM `textContent`, not `innerHTML`.
- [x] Fail-closed WSGI authentication supports legacy system `API_TOKEN` and an opt-in persistent credential registry with hashed tokens, expiry and revocation.
- [x] Local operator CLI issues, rotates and revokes credentials with transactionally recorded audit events; role escalation during rotation is blocked.
- [x] Tenant principals are derived only from verified server-side credentials; request-supplied tenant IDs are ignored.
- [x] Global compatibility graph is restricted to the fixed system administrator.
- [x] Tenant graph API uses a principal-bound SQLite store by default; tenant IDs cannot be reassigned by request input.
- [x] SQLite tenant graph first-read initialization is atomic and concurrency-tested.
- [x] PostgreSQL graph adapter and migration with RLS ENABLE + FORCE are implemented and integration-tested against PostgreSQL 16 using a separate NOSUPERUSER/NOBYPASSRLS runtime role.
- [x] Dry-run-first SQLite tenant migration utility creates private backups, checksums, validates snapshots, refuses overwrites by default, migrates all tenants in one transaction and verifies semantic read-back before commit.
- [x] Internal tenant document service with bounded PDF/DOCX/TXT parsing, private SQLite/FTS5 repository and resource-limited parser process; no HTTP routes or customer uploads are enabled.
- [x] Optional PostgreSQL document repository, composite tenant keys/FK, generated FTS vector, GIN index and RLS ENABLE + FORCE; CI verifies with a separate NOSUPERUSER/NOBYPASSRLS role.
- [x] PostgreSQL document/chunk schema with composite tenant keys, FORCE RLS, GIN full-text index and opt-in repository factory; integration-tested on PostgreSQL 16.
- [x] CI compiles and runs the full unit, API, security, storage and concurrency suite on Python 3.11 and 3.12, plus dependency audit.
- [x] LLM router external providers are deny-by-default; each primary/fallback must be listed in `LLM_ALLOWED_PROVIDERS`.
- [x] Autonomous worker prompt context is limited to a fixed public taxonomy; mutable global graph content is excluded from outbound worker prompts.

## Not yet production-ready
- [ ] Public account/credential provisioning, account recovery, self-service rotation and managed expiry/recovery policy. Local operator issue/rotate/revoke and audit are implemented, but do not replace public account lifecycle.
- [x] Documented PostgreSQL staging migration and rollback runbook with restricted roles, DSN priority and acceptance checklist.
- [ ] Run the migration utility against a production-like tenant backup; complete PostgreSQL staging cutover, rollback procedure and restore drill.
- [x] SQLite private-path hardening rejects symlinked ancestors and applies 0700/0600 permissions (TOCTOU/OS ownership limits documented).
- [ ] Independent adversarial review of tenant authorization and database RLS assumptions. The custom transaction-local PostgreSQL tenant setting is defense-in-depth, not a defense against SQL injection or arbitrary code execution under the application DB role.
- [ ] Production backup/restore, monitoring, alerting, secret rotation and incident response procedures.
- [x] Parser child clears inherited environment, applies restrictive umask and file-descriptor soft limit; it remains same-user process isolation.
- [ ] Before exposing the internal document service: add a low-privilege OS/container sandbox with no network, malware quarantine, document audit events, quotas, retention, object storage and secure backup/restore. The current worker is not a full sandbox.
- [ ] Production rehearsal of PostgreSQL document migration, tenant-filtered retrieval, RAG evaluation, provenance and source citations.
- [ ] CSRF protection for future browser state-changing endpoints.
- [ ] Rate limits and per-tenant/provider budgets.
- [ ] Centralized structured logs, metrics, traces and secret/PII redaction.
- [ ] Data classification, user notice/consent, ordinary-prompt PII/secret minimization, per-tenant provider policy, provider-specific retention/region controls and contractual/legal review. The router allowlist is deployment-level only.
- [ ] Dedicated single-owner autonomous worker with lease/coordination.
- [ ] Staging deployment and production smoke tests.
- [x] Python dependency license inventory and tracked-asset inventory generated; legal review of LGPL-3.0-only psycopg packages remains outstanding.

## Storage configuration

SQLite remains the default tenant backend. PostgreSQL is opt-in:

- `ISKRA_TENANT_STORAGE_BACKEND=sqlite` (default): uses the private tenant SQLite database.
- `ISKRA_TENANT_STORAGE_BACKEND=postgres`: requires `ISKRA_POSTGRES_DSN`, a pre-applied graph migration and a dedicated runtime role with `NOSUPERUSER NOBYPASSRLS`.
- `ISKRA_DOCUMENT_STORAGE_BACKEND=sqlite` (default): uses the private tenant document SQLite database.
- `ISKRA_DOCUMENT_STORAGE_BACKEND=postgres`: requires `ISKRA_POSTGRES_DSN`, pre-applied migration `0002_tenant_documents.sql` and the same restricted runtime role.

Do not enable PostgreSQL in production until staging migration, cross-tenant negative tests, backup/restore and rollback have passed. The PostgreSQL adapter is not automatically migrated and the application must never run as schema owner or superuser.

## Operational rules
- Use `wsgi:app` for public deployment. The `python app.py` development entry point now uses the same fail-closed middleware; do not expose Gunicorn `app:app`, which bypasses the production WSGI wrapper.
- Keep `ENABLE_AUTONOMOUS_LOOP=false` on web deployments.
- The supplied `render.yaml` uses one Gunicorn worker because the legacy global JSON graph relies on process-local locking. Do not increase the worker count or scale multiple web instances until that graph is moved to a shared transactional store and concurrency-tested.
- `render.yaml` does not provision a persistent disk or managed PostgreSQL database. The default `DATA_DIR` is the application directory; SQLite credential and tenant data must not be treated as durable on an ephemeral host. Before production, attach and verify durable storage or configure a managed database, then run backup/restore and restart tests.
- Never store API keys, database DSNs or raw bearer tokens in Git.
- Do not enable customer document uploads or RAG until authorization, storage isolation, retrieval filtering and restore tests pass.
- Keep the main restructuring PR in draft until reviewed; `main` must remain unchanged until a separate release decision.


## External LLM processing

The router now denies all registered external providers unless they are explicitly listed in `LLM_ALLOWED_PROVIDERS`; the same policy applies to primary and fallback. The Render manifest leaves this allowlist empty and sets `autoDeploy: false`. The autonomous worker uses a fixed public taxonomy rather than serializing the mutable global graph. Ordinary user prompts are not automatically redacted, provider allowlists are not tenant-specific, and no consent UI or network egress firewall exists. Customer-data processing by external LLMs remains NOT APPROVED pending provider-specific contractual/privacy review. See `LLM_PROVIDER_ALLOWLIST.md` and `LLM_PROVIDER_DATA_HANDLING.md`.
