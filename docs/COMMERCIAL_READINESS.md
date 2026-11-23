# Iskra AI — commercial readiness gate

**Status: NOT READY FOR SALE.** This document defines the evidence required before Iskra can be offered to paying customers. It does not claim legal compliance, security certification, validated product-market fit or production operation.

## 1. Product definition — decision required

Do not select a customer segment by assumption. Before building a paid offer, record:
- Primary buyer and daily user (which may differ).
- The costly or frequent problem Iskra solves.
- Current workaround and measurable disadvantage.
- One narrow initial use case and explicit non-goals.
- Expected outcome and acceptance criteria.
- Evidence from at least five discovery interviews with representative prospective users; record date, role, problem frequency, current spend/workaround and willingness-to-pilot. Interviews are discovery evidence, not proof of market demand.
- Named product owner and support owner.

**Gate:** a written one-page product brief approved by the project owner. Until then, pricing and market claims remain hypotheses.

## 2. MVP scope and customer promise

Define and freeze a narrow MVP before accepting customers:
- Supported workflows and languages.
- Supported model providers and regions.
- Data types, file limits, retention and deletion behavior.
- Availability target and support hours.
- Explicit exclusions (including autonomous actions, unsupported integrations and beta document/RAG features).
- Demo script using synthetic data only.
- Acceptance tests for the top three customer workflows, failure states and recovery.
- A clear status page/release notes process.

Do not advertise a capability merely because a module or prototype exists in the repository.

## 3. License and intellectual-property inventory

Create a machine-readable and human-reviewed inventory covering:
- Direct and transitive Python packages, pinned versions and SPDX license identifiers.
- Model provider terms, model/version identifiers, commercial-use rights, output terms, retention/training settings and geographic processing.
- Embedding models, tokenizer/model weights and datasets.
- Fonts, icons, images, templates, sample documents and copied code.
- Any source code generated from or adapted from third-party repositories.

For every item record source URL, version/hash, license/terms URL, commercial-use permission, attribution obligations, redistribution restrictions, copyleft obligations, data-use terms, reviewer and review date.

**Gate:** no unresolved license conflict, no unreviewed asset, and required notices/attributions shipped with the product. A dependency audit alone is not a legal license opinion.

## 4. Privacy and data protection

Before real customer data is accepted, document:
- Data-flow map: collection, purpose, storage, model/provider transfer, subprocessors, access, retention, deletion and backup expiry.
- Controller/processor roles for each deployment model; customer contract and DPA where applicable.
- Lawful basis and transparency information determined with qualified privacy counsel.
- Data minimization, purpose limitation, access controls and tenant isolation.
- Data subject request process: access, export, correction, deletion and response tracking.
- Retention schedule covering primary DB, logs, vector stores, backups and provider-side retention.
- Subprocessor list, processing locations, international transfer assessment where relevant.
- Incident/breach triage, escalation and notification decision procedure.
- DPIA screening and a DPIA where required.
- Separate policy for telemetry and model-provider prompts; redact secrets and personal data from logs.

**Gate:** privacy documentation and contracts reviewed for the actual operating model by qualified counsel. Do not claim GDPR compliance based only on this checklist.

## 5. Security and operational controls

Required evidence:
- Independent review of authentication, authorization, tenant boundaries and PostgreSQL RLS assumptions.
- Negative cross-tenant tests for read, write, list, search, export and delete.
- Credential issue/rotation/revocation, least privilege and operator audit.
- Secret manager, rotation procedure and no secrets in Git or logs.
- TLS, secure proxy configuration, security headers, CSRF protection for browser mutations.
- Rate limits and tenant/provider usage budgets with abuse controls.
- Parser isolation in a dedicated low-privilege sandbox; malware quarantine before document processing.
- Encryption in transit and at rest, key ownership/rotation and backup encryption.
- Durable storage, automated backup, restore and rollback drills with recorded RPO/RTO.
- Monitoring, structured logs, metrics, traces, alert routing and PII/secret redaction.
- Incident response runbook, on-call owner and a tabletop exercise.
- Dependency and vulnerability review, patch cadence and release rollback procedure.

**Gate:** staging evidence on one integrated release SHA, not isolated feature branches.

## 6. Reliability and support

Define before sale:
- Service availability target and measurement method.
- Support channels, hours, severity levels and response targets.
- Escalation and incident communication process.
- Backup frequency, tested restore procedure, RPO and RTO.
- Maintenance windows, upgrade policy and deprecation policy.
- Customer offboarding, export and verified deletion.
- Status page and known-issues register.

Do not publish an SLA until the hosting topology and monitoring can support it.

## 7. Cost model and pricing

Build a per-customer unit economics worksheet using measured workloads:
- Model input/output tokens by workflow, provider, retries and fallback frequency.
- Embeddings, vector/database, storage, egress and backups.
- Hosting, observability, email and support labor.
- Expected concurrency, peak load, abuse and safety margin.
- Free trial cost cap, per-tenant quotas and hard spend ceiling.
- Gross margin under low, expected and high usage.
- Price metric (seat, usage, workspace or hybrid) and overage behavior.

Record provider price source/date and assumptions. Do not publish prices until measured pilot usage and current provider costs are available. Add an emergency spend stop and customer-visible usage reporting.

## 8. Onboarding and customer operations

Minimum launch package:
- Setup guide and secure first-admin provisioning.
- Tenant creation, invitation and role management.
- Provider configuration with secret handling.
- Quick-start tutorial and synthetic demo workspace.
- Data export/deletion instructions.
- Troubleshooting and known limitations.
- Terms of service, privacy notice, DPA if applicable, subprocessors and support policy.
- Release notes, versioning and upgrade/rollback guide.

## 9. Release acceptance checklist

A release can be considered **commercial-candidate** only when every item below has linked evidence:
- [ ] Approved product brief and target segment evidence.
- [ ] MVP scope, demo and acceptance tests.
- [ ] License and IP inventory reviewed.
- [ ] Privacy/data-flow and contract review completed.
- [ ] Security review and cross-tenant negative tests passed.
- [ ] One integrated SHA passes full CI and dependency/security audit.
- [ ] Production-like staging smoke, concurrency, restart and failure tests passed.
- [ ] Backup, restore and rollback drill passed against durable storage.
- [ ] Observability, alerts and incident response tested.
- [ ] Cost model, quotas, spend limits and pricing approved.
- [ ] Onboarding, support, terms and customer documentation ready.
- [ ] Named operational owner and support owner confirmed.

## 10. Current known blockers — verified 2026-11-23

The current integrated release candidate is branch `integration/full-release-candidate-v1`. PR #89 was squash-merged into this branch at commit `f03254204e1c22b0c8f16a2a1661446ebb529fb8`; the canonical `refactor/modular-core` branch and `main` have not been changed.

At the exact merge commit, all five GitHub workflows passed:
- Unified quality gates [45227417701](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45227417701): SUCCESS — 337 tests on Python 3.11 and 337 tests on Python 3.12, plus dependency vulnerability audit.
- Security/reliability [45227417710](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45227417710): SUCCESS.
- Quality Engine [45227417619](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45227417619): SUCCESS.
- Adversarial corpus [45227417647](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45227417647): SUCCESS.
- Dependency/license inventory [45227417663](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45227417663): SUCCESS.

Documentation was updated after this merge to reflect the integrated branch status. Re-run the same five workflows on the latest branch head before promoting it into the canonical integration branch.

The repository still has **no verified production deployment and is NOT READY FOR SALE**. No live customer data, real provider calls, paid infrastructure or production secrets were used. The current feature remains a controlled-pilot foundation.

Remaining blockers:
- No production-like staging PostgreSQL cutover, durable hosting volume, backup/restore/rollback rehearsal or production smoke test.
- The license inventory reports 28 Python distributions; psycopg and psycopg-binary are LGPL-3.0-only and require qualified legal/distribution review. No full IP/license clearance has been completed.
- The tenant provider allowlist is a technical deny-by-default control, not a consent record or lawful-basis assessment. No consent UI, provider-specific DPA/region/retention verification or network egress firewall exists. External customer-data processing remains NOT APPROVED pending provider-specific contractual/privacy review.
- Outbound minimization is best-effort regex coverage for tenant-chat questions/excerpts; it is not complete DLP, anonymization or coverage of every prompt path.
- The parser worker has environment/resource hardening but is not a full OS/container sandbox. Customer uploads remain disabled pending sandboxing, malware quarantine, audit, quotas, retention and restore controls.
- SQLite credential storage is single-instance; production horizontal scaling requires a reviewed PostgreSQL credential backend. Parent-directory protection trusts processes running as the same service UID.
- No public signup, MFA, account recovery, email verification, billing/quotas, validated pricing/cost model, customer onboarding, support/SLA, incident response or sales acceptance evidence.
- No product-market validation interviews have been completed and no target segment or pricing has been approved.

Recheck these findings against current evidence before each release decision; this list is a verified snapshot, not a permanent assertion.

## Change control

- GitHub is the source of truth for code and release evidence.
- Work on isolated branches based on `refactor/modular-core`.
- Keep PRs Draft until reviewed.
- Do not modify `main`, merge PRs, publish a release, incur paid costs or deploy without a separate explicit authorization.
- Report technical readiness separately from legal, operational and commercial readiness.
- **SUCCESS** requires all critical gates to be evidenced. If a customer decision, legal review, secret, paid account or production access is required, mark it as a blocker rather than inventing completion.
