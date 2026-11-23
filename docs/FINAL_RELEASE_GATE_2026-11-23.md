# Iskra AI — final release gate (2026-11-23)

Status: **BLOCKED — not production-ready**.

This checklist is an evidence-based release gate. Do not mark items complete without an attached run, deployment record, or reviewer evidence.

## P0 — Security and service integrity
- [ ] Implement and integrate durable PostgreSQL credential/session storage; keep authentication fail-closed.
- [ ] Verify CSRF protections on every browser state-changing route.
- [ ] Verify tenant isolation with negative read/write/delete tests against a production-like database and runtime role (NOSUPERUSER, NOBYPASSRLS).
- [ ] Verify credential rotation, expiry, revocation and audit-event behavior.
- [ ] Confirm secrets are absent from logs, repository, backups and error responses.
- [ ] Review dependency and container/hosting configuration; resolve critical/high findings.

## P0 — Deployment and recovery
- [ ] Provision staging with managed PostgreSQL and durable storage.
- [ ] Verify TLS, proxy headers, security headers, health checks and least-privilege secrets.
- [ ] Run migration rehearsal and semantic read-back verification on staging data.
- [ ] Complete rollback rehearsal.
- [ ] Complete encrypted backup and restore drill; verify recovery point/time objectives.
- [ ] Confirm single-worker/singleton constraints or replace legacy process-local graph with shared storage/coordination.

## P1 — Customer data and RAG
- [ ] Keep ingestion disabled until parser sandbox is isolated (low privilege, no network), malware quarantine, retention, quotas, audit and restore are validated.
- [ ] Verify tenant-bound retrieval, source citations, deletion semantics and prompt-injection handling.
- [ ] Test outbound provider minimization and provider allowlist/cost controls.

## P1 — Operations and product readiness
- [ ] Central structured logs, metrics, alert routing, redaction and incident runbook.
- [ ] Dedicated autonomous-worker deployment with lease/coordination, safe shutdown and monitoring; keep disabled on web instances.
- [ ] Public onboarding, account recovery, MFA, billing and support policies if commercial SaaS launch is intended.
- [ ] Legal/privacy/provider terms review and license inventory.

## Release acceptance
- [ ] CI passes on supported Python versions and PostgreSQL integration tests.
- [ ] Independent security review completed and findings closed or formally accepted.
- [ ] Staging smoke test and recovery drill passed.
- [ ] Release tag, immutable artifact, changelog and installation/deployment instructions created.
- [ ] Production deployment verified by operator.

A green CI pipeline is not a production certification. Release status can change to **READY** only after all P0 gates and applicable P1 launch gates have evidence and explicit operator approval.
