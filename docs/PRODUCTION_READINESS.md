# Iskra AI — production readiness

This checklist is intentionally conservative. The modular refactor does not by itself make the application a secure multi-tenant SaaS.

## Current verified baseline
- [x] Existing Flask routes retained.
- [x] Twelve foundational graph pillars retained by the existing graph model.
- [x] Knowledge graph and provider router extracted into Python packages.
- [x] Runtime port and data directory validated.
- [x] Dashboard graph labels are rendered with DOM `textContent`, not `innerHTML`.
- [x] Baseline security headers added.
- [x] Tenant-scoped transactional SQLite graph adapter added and tested; it is not yet wired into the live Flask application.
- [x] Existing deterministic tests run on Python 3.11 and 3.12 in GitHub Actions.
- [x] Existing multi-thread/process stress suite run in GitHub Actions.

## Not yet production-ready
- [ ] Authentication, account lifecycle, and authorization.
- [ ] Tenant-scoped data model and isolation tests.
- [ ] Durable transactional PostgreSQL persistence and migration/rollback; the SQLite adapter is a tested migration step, not a production tenant-isolation guarantee.
- [ ] Private document upload, malware/type/size validation, and secure object storage.
- [ ] Tenant-filtered retrieval, RAG evaluation, and source citations.
- [ ] CSRF protection for future state-changing browser endpoints.
- [ ] Rate limits on public endpoints and per-tenant/provider budgets.
- [ ] Centralized structured logs, metrics, traces, and secret/PII redaction.
- [ ] Dedicated single-owner worker and lease for autonomous jobs.
- [ ] Staging deployment, backup/restore drill, and production smoke tests.

## Operational rules
- Keep `ENABLE_AUTONOMOUS_LOOP=false` on web deployments.
- Do not run multiple Gunicorn workers against JSON storage and assume process-local locks are sufficient. The current POSIX file lock is a compatibility safeguard, not a substitute for database transactions.
- Never store API keys in Git. Configure them as hosting secrets.
- Do not upload customer confidential information until authentication, tenant isolation, durable storage, and access-controlled retrieval have passed tests.
- Keep this branch separate until the draft PR has been reviewed and all required checks are green.
