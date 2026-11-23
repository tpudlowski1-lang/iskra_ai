# Product-market hypothesis — Iskra AI (draft, unvalidated)

**Status:** Working hypothesis for discovery, not an approved product specification, price list or claim of current functionality.

## 1. Initial customer hypothesis

Start with Polish-language professional service firms with approximately 10–50 employees, especially small IT consultancies, software/service agencies and specialist B2B consultancies.

Likely buyer: founder, managing partner or operations lead. Likely daily users: consultants, project leads and new employees.

Why this segment first:
- Knowledge work depends on internal procedures, project decisions, reusable answers and onboarding material.
- Teams are large enough to experience knowledge fragmentation but small enough for a single-tenant pilot and direct founder-led sales.
- Avoid regulated/high-sensitivity verticals (health, legal, financial advice) as the first pilot until privacy, contractual and operational controls are independently reviewed.

This is a hypothesis. No customer interviews, letters of intent or paid pilots have yet validated it.

## 2. Problem to validate

The proposed problem is not "companies need another chatbot". It is:

> Small knowledge-intensive teams repeatedly lose time searching for internal procedures, project notes and approved answers; onboarding depends on a few experienced people; existing documents are fragmented across folders and tools.

Discovery interviews must test:
- How often people search for internal information and how long it takes.
- Which documents are authoritative and who owns them.
- Whether teams already pay for a wiki, search or AI tool.
- Which data must never leave their infrastructure.
- Who approves deployment, security and AI provider terms.
- What measurable outcome would justify a paid pilot.

## 3. MVP hypothesis

A narrow, single-organization knowledge assistant with:
1. Admin-curated document import (PDF/DOCX/TXT only after parser sandbox, malware controls and tenant authorization are complete).
2. Search and answer grounded in source passages, with citations and a clear "not found" response.
3. One organization boundary, named users and role-based access before any customer data is accepted.
4. Deployment-level provider allowlist, empty by default; local-only mode only if independently implemented and tested.
5. Data retention, deletion, export, backup and audit trail.
6. Polish-first UI and documentation.

Do not include in MVP:
- Public/self-service multi-tenant SaaS signup.
- Autonomous background learning on customer data.
- Customer-facing file uploads before sandbox and access-control gates.
- External integrations/connectors until per-source permissions and audit are implemented.
- Billing automation until cost metering and quotas are verified.

## 4. Proposed differentiation — to prove, not assume

- Polish-first workflows and explanations.
- Private/single-tenant deployment options.
- Transparent provider choice and outbound-data policy.
- Source-grounded answers rather than unsupported free-form chat.
- Explicit "no answer" behavior when the knowledge base does not support a claim.

These are product hypotheses; the current codebase does not yet satisfy the full MVP list. In particular, RAG ingestion and customer uploads remain disabled, ordinary prompts are not automatically redacted, per-tenant provider policy is incomplete, and no production deployment has been verified.

## 5. Market evidence (directional only)

Eurostat's 2026 Digitalisation in Europe publication reports that in 2025:
- 20% of EU businesses used AI technologies.
- Poland was among the lowest-adoption countries at approximately 8%.
- 19% of EU SMEs used AI, compared with 55% of large businesses.

Source: [Eurostat — Digitalisation in Europe, 2026 edition](https://ec.europa.eu/eurostat/web/interactive-publications/digitalisation-2026), section "Technology uptake in businesses / AI".

Interpretation:
- Poland's lower adoption may indicate room for simple, well-scoped solutions, but it may also indicate lower readiness, skills or willingness to pay.
- EU-wide SME figures cannot be presented as Poland-specific SME adoption.
- General AI adoption does not prove demand for an internal knowledge assistant.
- Competitor pricing and feature claims need a separate verification against official vendor pricing pages before setting Iskra pricing.

## 6. Commercial model hypothesis

Begin with a founder-led, paid pilot rather than a self-service SaaS subscription:
- One-time deployment/configuration fee.
- Fixed monthly support/maintenance fee.
- Model/API costs passed through or capped transparently.
- Clear usage limits and an agreed data-processing scope.

Do not publish a price until:
- Infrastructure, model tokens, support hours and backup costs are measured.
- A pilot scope and target customer are validated.
- The license/IP review is complete.
- The customer-data and provider-contractual model is approved.

## 7. Validation gates before product approval

1. Complete at least 10 structured discovery interviews with the target segment.
2. Confirm one repeatable, high-frequency knowledge problem and the document sources needed.
3. Obtain at least 3 design-partner commitments; target at least 1 paid pilot before building broad SaaS features.
4. Measure baseline time-to-answer, answer acceptance, citation coverage and weekly active usage.
5. Validate deployment and support cost for one pilot.
6. Obtain privacy/security review and signed provider/data-processing terms before any customer data is sent externally.

## 8. Decision rule

Proceed with this segment only if interviews show a frequent, expensive problem and at least one buyer is willing to fund a constrained pilot. Otherwise revise the segment or problem before expanding engineering scope.

No market-fit, pricing, legal-compliance or sale-readiness claim is made by this document.


## 9. Critical current product gap — verified in code audit

The current Flask application is not yet a usable conversational assistant:
- The web UI is a knowledge-graph dashboard, not a chat interface.
- The HTTP API exposes graph/health endpoints; there is no authenticated chat endpoint.
- RouterProvider is used by the optional autonomous worker, but there is no end-user request path that calls it.
- DocumentService has tenant-scoped add/list/search/delete methods, but those methods are not wired into authenticated HTTP document routes or a retrieval-to-answer pipeline.
- There is no source-grounded answer endpoint or end-user chat history.

Therefore the product MVP described above is a future target, not the current build. The next feature milestone must implement an authenticated tenant-scoped chat API and UI, connect document search to answer generation with citations and an explicit no-answer path, and add end-to-end tests for cross-tenant isolation and provider policy. Keep customer document ingestion disabled until parser sandboxing, file validation, authorization and operational controls are complete.
