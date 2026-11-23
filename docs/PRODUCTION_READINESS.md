# Iskra AI — production readiness

This checklist is intentionally conservative. Passing CI does not by itself make Iskra a production-ready multi-tenant SaaS.

## Current verified baseline
- [x] Existing Flask compatibility routes and twelve foundational graph pillars retained.
- [x] Modular configuration, knowledge graph, LLM router, API, security headers and autonomous worker boundaries.
- [x] Dashboard renders graph labels with DOM `textContent`, not `innerHTML`.
- [x] Fail-closed WSGI authentication supports legacy system `API_TOKEN` and an opt-in persistent credential registry with hashed tokens, expiry and revocation.
- [x] Tenant principals are derived only from verified server-side credentials; request-supplied tenant IDs are ignored.
- [x] Global compatibility graph is restricted to the fixed system administrator.
- [x] Tenant graph API uses a principal-bound SQLite store by default; tenant IDs cannot be reassigned by request input.
- [x] SQLite tenant graph first-read initialization is atomic and concurrency-tested.
- [x] PostgreSQL graph adapter and migration with RLS ENABLE + FORCE are implemented and integration-tested against PostgreSQL 16 using a separate NOSUPERUSER/NOBYPASSRLS runtime role.
- [x] CI compiles and runs the full unit, API, security, storage and concurrency suite on Python 3.11 and 3.12, plus dependency audit.

## Not yet production-ready
- [ ] Public account/credential provisioning, account recovery, self-service rotation, expiry policy and auditable credential lifecycle.
- [ ] PostgreSQL staging cutover, repeatable JSON/SQLite migration, rollback procedure and restore drill.
- [ ] Independent adversarial review of tenant authorization and database RLS assumptions. The custom transaction-local PostgreSQL tenant setting is defense-in-depth, not a defense against SQL injection or arbitrary code execution under the application DB role.
- [ ] Production backup/restore, monitoring, alerting, secret rotation and incident response procedures.
- [ ] Private document upload, malware/type/size validation and secure object storage.
- [ ] Tenant-filtered retrieval, RAG evaluation, provenance and source citations.
- [ ] CSRF protection for future browser state-changing endpoints.
- [ ] Rate limits and per-tenant/provider budgets.
- [ ] Centralized structured logs, metrics, traces and secret/PII redaction.
- [ ] Dedicated single-owner autonomous worker with lease/coordination.
- [ ] Staging deployment and production smoke tests.

## Storage configuration

SQLite remains the default tenant backend. PostgreSQL is opt-in:

- `ISKRA_TENANT_STORAGE_BACKEND=sqlite` (default): uses the private tenant SQLite database.
- `ISKRA_TENANT_STORAGE_BACKEND=postgres`: requires `ISKRA_POSTGRES_DSN`, a pre-applied migration and a dedicated runtime role with `NOSUPERUSER NOBYPASSRLS`.

Do not enable PostgreSQL in production until staging migration, cross-tenant negative tests, backup/restore and rollback have passed. The PostgreSQL adapter is not automatically migrated and the application must never run as schema owner or superuser.

## Operational rules
- Use `wsgi:app` for public deployment; direct `app:app` bypasses authentication middleware.
- Keep `ENABLE_AUTONOMOUS_LOOP=false` on web deployments.
- Do not run multiple Gunicorn workers against the legacy JSON global graph and assume process-local locks are sufficient.
- Never store API keys, database DSNs or raw bearer tokens in Git.
- Do not enable customer document uploads or RAG until authorization, storage isolation, retrieval filtering and restore tests pass.
- Keep the main restructuring PR in draft until reviewed; `main` must remain unchanged until a separate release decision.
