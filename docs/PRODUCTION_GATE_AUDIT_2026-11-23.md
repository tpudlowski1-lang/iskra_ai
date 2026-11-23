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
| Automated CI and dependency audit | PARTIAL | Draft PR #67 now integrates the canonical code/documentation scopes from PRs #47, #49, #53, #55–#60, #63 and #66 into one release-candidate HEAD `290de597810e9e3627a70df9aafb68476db1e521`. On this shared HEAD, the unified suite passes 248 tests on Python 3.11 and 248 on Python 3.12; dependency audit, Quality Engine, Security/Reliability and Adversarial Corpus workflows also pass. This is a draft integration candidate, not an approved release or production deployment. |
| WSGI authentication | PARTIAL | PR #67 includes the integrated PR #66 WSGI auth, direct-development entrypoint and reserved system-admin boundary; the full integrated suite passes 248 tests on each Python version. Authentication rejects legacy persistent credential rows with tenant_id `system`. Source/duplicate PRs #50–#52, #62, #64 and #65 must not be merged independently while #67 is reviewed. Live host secrets, persistent credential DB, TLS and operator provisioning have not been verified. |
| Identity, roles and tenant boundaries | PARTIAL | Principal-bound APIs and PostgreSQL FORCE RLS are integration-tested in CI using a separate NOSUPERUSER/NOBYPASSRLS role. PR #66 additionally reserves global access to the exact SYSTEM_ADMIN singleton and rejects both new and legacy persistent tenant credentials claiming `system`. Independent security review is outstanding. The transaction-local custom tenant setting is defense-in-depth, not protection against SQL injection or arbitrary code execution under the DB role. |
| PostgreSQL migrations | PARTIAL | PR #67 includes the PR #59 combination of strict SQLite integrity/foreign-key preflight, lossless migration validation, checksum-verified restore and corrected PostgreSQL architecture/migration policy. The combined full suite passes 248 tests on each Python version. This still does not prove production-like cutover, semantic verification of a live tenant dataset, or a completed rollback drill. |
| Backup and recovery | PARTIAL | PR #54 verifies/restores one tenant-graph SQLite file; PR #59 combines that restore with strict migration validation. PR #67 includes the PR #63 configuration-aware backup inventory on top of the PR #61 JSON/SQLite archive/restore tool. It discovers only validated local Iskra stores and fails closed when PostgreSQL is active. The integrated full suite passes 248 tests on each Python version. The tool requires operator-confirmed quiescence, does not back up PostgreSQL, external object storage or hosting secrets, and SHA-256 checks corruption rather than archive authenticity. Encryption/signing and a durable-volume production restore drill remain external release gates. |
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
- PR #67 full release-candidate unified CI, HEAD `290de597810e9e3627a70df9aafb68476db1e521`: [45117333096](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45117333096)
- PR #67 adversarial corpus integrity: [45117333063](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45117333063)
- PR #67 Quality Engine: [45117333093](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45117333093)
- PR #67 Security/Reliability: [45117333091](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45117333091)
- PR #61 full JSON/SQLite backup archive and restore, current HEAD `c756a8e7788116a1d786e4951ed6a3648e171e4c`: [45115688245](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115688245)
- PR #63 configuration-aware backup inventory, HEAD `c9cf328441f0757298b54fda5cc4fbf064ba895c`: [45115618264](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45115618264)

A green CI run proves only the tests executed for that commit. It does not prove production hosting, real secret configuration, persistent storage, staging recovery, live LLM safety or deployment readiness.

## Required closure sequence

1. Review PR #67 as the single integrated release-candidate branch. Reconcile its source/duplicate PRs #27, #47–#66; do not merge source PRs independently. Require independent code/security review and explicit merge authorization before any merge.
2. The complete suite (248 tests on Python 3.11 and 3.12), dependency audit, Quality Engine, Security/Reliability and Adversarial Corpus workflows passed on code HEAD `290de597810e9e3627a70df9aafb68476db1e521`; rerun them after any runtime-code changes.
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
