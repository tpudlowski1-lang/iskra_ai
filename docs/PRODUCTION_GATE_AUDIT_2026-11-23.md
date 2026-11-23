# Iskra AI — production gate audit (2026-11-23)

## Executive decision

**Overall status: NOT PRODUCTION READY.** The modular core has a strong automated test foundation and useful security/storage controls, but the production gate is not closed. No production environment, persistent volume, real credentials, external backup/restore, staging cutover or operational monitoring was verified in this audit.

This report is a snapshot of repository evidence, not a penetration test, deployment attestation or certification.

## Source of truth and change control

- GitHub repository is the sole source of truth for code, architecture, branches, tests, PRs and releases.
- Audit baseline: `refactor/modular-core` at `6b49760a2274464c1b0f787b850f60c8c4e014f8`.
- `main` was observed at `7f34c5a22a0b781039d026f145307418280b8369` and was not changed.
- Draft PRs are not part of the baseline until reviewed and merged. No PR was merged and no deployment was performed.
- Linear, Notion and PostHog are supporting tools only; they do not replace GitHub.

## Gate results

| Gate | Status | Evidence and remaining work |
|---|---|---|
| Automated CI and dependency audit | PARTIAL | Draft PRs #47–#66 have targeted/full CI successes on their respective heads, including integrated WSGI/system-identity validation in PR #66, migration/restore validation in PR #59, and configuration-aware local backup planning in PR #63. There is not yet one integrated final release SHA containing all approved changes. |
| WSGI authentication | PARTIAL | PR #66 combines current PR #50 WSGI auth, direct-development entrypoint hardening and the reserved system-admin boundary on one branch; it passes 196 tests on Python 3.11/3.12 plus dependency audit. It also rejects legacy persistent credential rows with tenant_id `system`. PR #51 is stale and PRs #62/#65 are source/duplicate branches; do not merge them independently. Live host secrets, persistent credential DB, TLS and operator provisioning have not been verified. |
| Identity, roles and tenant boundaries | PARTIAL | Principal-bound APIs and PostgreSQL FORCE RLS are integration-tested in CI using a separate NOSUPERUSER/NOBYPASSRLS role. PR #66 additionally reserves global access to the exact SYSTEM_ADMIN singleton and rejects both new and legacy persistent tenant credentials claiming `system`. Independent security review is outstanding. The transaction-local custom tenant setting is defense-in-depth, not protection against SQL injection or arbitrary code execution under the DB role. |
| PostgreSQL migrations | PARTIAL | PR #59 combines PR #52 strict SQLite integrity/foreign-key preflight and lossless migration validation with PR #54 checksum-verified backup/restore, and includes the corrected PostgreSQL architecture/migration policy. Its architecture-integrated HEAD `576e58f4...` passes 190 tests on Python 3.11 and 3.12 plus dependency audit. It still does not prove production-like cutover, semantic verification of a live tenant dataset, or a completed rollback drill. |
| Backup and recovery | PARTIAL | PR #54 verifies/restores one tenant-graph SQLite file; PR #59 combines that restore with strict migration validation. PR #61 adds an explicit-allowlist archive/restore tool for JSON and SQLite and passes full CI on current HEAD `c756a8e7...` (Python 3.11/3.12, 200 tests each). PR #63 stacks a configuration-aware inventory mode on that tool, discovers only validated local Iskra stores, and fails closed when PostgreSQL is active; its full CI passes 203 tests on each Python version plus dependency audit. The tool requires operator-confirmed quiescence, does not cover PostgreSQL/object storage/hosting secrets, and SHA-256 is not archive authenticity. No durable-volume or production restore drill was performed. |
| Document ingestion and RAG | BLOCKED for public use | The document service has no HTTP routes and no generated RAG answers. The parser runs in a resource-limited child process but under the same OS user; there is no full OS/container sandbox, malware quarantine, object storage, encryption-key lifecycle, retention scheduler or full audit pipeline. Public uploads/RAG must remain disabled. |
| Hosting and persistence | BLOCKED | The baseline `render.yaml` uses two Gunicorn workers while the legacy global graph has process-local constraints; PR #53 changes it to one worker and passes CI. The manifest does not provision a persistent disk or managed PostgreSQL. No live Render configuration, volume, secrets, TLS, restart persistence or deployment was inspected. |
| Credentials lifecycle | PARTIAL | SQLite registry stores token digests and supports issue/rotate/revoke/expiry with audit events. Public account provisioning/recovery, managed lifecycle and a durable production credential store are not complete. PR #66 blocks legacy persistent rows that claim the reserved `system` tenant. Render's legacy `API_TOKEN` represents the system administrator; tenant credentials need a separately provisioned persistent registry. |
| Secrets and repository hygiene | PARTIAL | Existing `.gitignore` rules are extended in PR #56 to cover credentials DBs, private documents, backups and local runtime artifacts. PR #56 CI passes, but it remains Draft and is not yet in the baseline. Hosting secret rotation has not been tested. |
| LLM routing and provider reliability | PARTIAL | PR #48 tests provider exception fallback. Live provider credentials, quotas, cost controls, invalid-schema handling and real upstream availability have not been validated. The adversarial corpus in PR #49 is structural test data; it is not a semantic LLM safety pass. |
| Observability and incident response | BLOCKED for production operations | PostHog is connected as a tool but has not been instrumented in Iskra. No verified central structured logs, metrics, traces, alert routing, secret/PII redaction or incident-response drill. Datadog is not connected; this is not a code blocker by itself. |
| Autonomous worker | PARTIAL | Web startup keeps the autonomous loop disabled. Explicit worker role is required, but a dedicated single-owner worker with lease/coordination and operational monitoring is not verified. |
| Web/API hardening | PARTIAL | Security headers and request-size limits exist. Rate limits/per-tenant budgets are not wired; CSP still permits inline script/style for the current dashboard, and HSTS/proxy configuration has not been verified. CSRF is a future gate for browser state-changing routes. |

## CI evidence checked

All runs below were observed as completed/success on their specific PR heads:

- PR #47 Quality Engine: [45107678207](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45107678207)
- PR #48 Security & Reliability: [45108077117](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45108077117)
- PR #49 adversarial corpus integrity: [45109641744](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45109641744)
- PR #66 integrated WSGI, development entrypoint and system identity boundary, HEAD `cf3b2044116911fb2b3a8a9ed24fedaecdf1a360`: [45116183798](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45116183798)
- PR #27 corrected PostgreSQL architecture and migration docs: [45115287908](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115287908)
- PR #52 strict migration validation: [45112445030](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45112445030)
- PR #53 Render single-worker contract: [45112296368](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45112296368)
- PR #54 verified SQLite restore: [45113522451](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45113522451)
- PR #55 independent document backend selection: [45113445185](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45113445185)
- PR #57 full backup/recovery inventory documentation: [45113854647](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45113854647)
- PR #56 repository hygiene, final reviewed HEAD `7e63019cc5ab7cc95f99b1346d6553b745580fd0`: [45113990484](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45113990484)
- PR #59 integrated migration + verified restore and corrected architecture docs, HEAD `576e58f4ab32184e296a71cd62ca6d952a784510`: [45115356552](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115356552)
- PR #60 commercial readiness gate documentation: [45114251107](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45114251107)
- PR #66 integrated WSGI/system identity security, HEAD `cf3b2044116911fb2b3a8a9ed24fedaecdf1a360`: [45116183798](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45116183798)
- PR #61 full JSON/SQLite backup archive and restore, current HEAD `c756a8e7788116a1d786e4951ed6a3648e171e4c`: [45115688245](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115688245)
- PR #63 configuration-aware backup inventory, HEAD `c9cf328441f0757298b54fda5cc4fbf064ba895c`: [45115618264](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115618264)

A green CI run proves only the tests executed for that commit. It does not prove production hosting, real secret configuration, persistent storage, staging recovery, live LLM safety or deployment readiness.

## Required closure sequence

1. Review and integrate PRs #47–#66 in a controlled order. Use PR #66 as the integrated WSGI/system-identity candidate, PR #59 as the combined migration/restore/documentation candidate, and PR #63 as the configuration-aware backup follow-up stacked on PR #61. Reconcile source/duplicate PRs #27, #50–#52, #62, #64 and #65; keep all Draft until review and explicit merge authorization.
2. Run the complete suite and dependency audit on one final integrated SHA.
3. Complete an independent tenant authorization/RLS review and negative tests against the production-like DB role.
4. Configure a persistent volume or managed PostgreSQL and run staging migration, semantic read-back, backup, restore and rollback drills.
5. Add a dedicated low-privilege parser container/OS sandbox, malware quarantine, private object storage, encryption, retention and audit before exposing documents.
6. Keep customer uploads and RAG disabled until retrieval isolation, prompt-injection evaluation, evidence grounding and citations pass.
7. Configure and verify host secrets, TLS/HSTS, durable storage, worker topology, quotas, structured observability, alerts and incident response.
8. Run staging smoke, restart, concurrency, failure and recovery tests.
9. Record the final SHA and evidence in GitHub. Only then can the product gate be considered for SUCCESS.

## Non-negotiable safety boundaries

- Do not modify `main` as part of this audit.
- Do not merge PRs or deploy without a separate explicit release decision.
- Do not enable public uploads or RAG before the document security gates pass.
- Do not label a targeted test suite or a green isolated PR as full product SUCCESS.
