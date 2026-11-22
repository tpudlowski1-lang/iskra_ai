# Iskra quality gates and modernization plan

This document describes verification and modernization for the current Flask neural-graph application. It does not claim that unimplemented product capabilities already exist.

## Current verified baseline

- Flask application with a 12-pillar in-memory knowledge graph persisted to a JSON file.
- JSON-based provider router for OpenAI-compatible chat completions, DeepSeek and Gemini.
- /health, /api/network and dashboard routes.
- Existing multithread tests exercise 200 graph updates and 1,000 concurrent HTTP requests.
- The current persistence lock is process-local. It does not coordinate multiple Gunicorn worker processes.
- The current application has no chat endpoint, tenant model, durable database abstraction, vector retrieval pipeline, tool permission system or agent execution API. Those must be designed and implemented before claiming those capabilities.

## Test layers

1. Unit and contract tests: graph invariants, provider routing, response parsing and API response schemas.
2. Persistence tests: clean initialization, save/reload, corrupt-file recovery and atomic-write behavior.
3. Concurrency tests: thread contention now; multi-process and shared-store tests only after persistence is moved behind a process-safe backend.
4. Resilience tests: provider timeout, rate limit, malformed payload, unavailable provider, retry budget and fallback ordering using mocked HTTP.
5. Security tests: authentication/authorization, input bounds, secret redaction, unsafe dashboard rendering, prompt injection and retrieval-scope isolation when those surfaces exist.
6. Load and soak tests: k6 or Locust against a deployed staging instance, with explicit request-rate and duration budgets.
7. AI quality evaluations: fixed Polish test corpus, factuality/grounding, refusal behavior, retrieval precision/recall and tool-call correctness. Model-graded tests must be versioned and compared to a baseline.

## Proposed integration order

- Keep the existing graph and Dekalog-oriented identity as the domain core.
- Introduce a storage interface and migrate JSON persistence to SQLite for a single-instance deployment or PostgreSQL for multiple workers / multiple tenants. Use database transactions and uniqueness constraints; a Python RLock is not a cross-process lock.
- Keep the provider router behind a stable interface. Add provider capability metadata, per-provider timeout/retry budgets, circuit breakers, structured errors and cost/token accounting. Never silently switch providers without recording which one answered.
- Add OpenTelemetry traces, metrics and structured logs. Initialize instrumentation after Gunicorn worker fork; redact prompts, credentials and personal data before export.
- Add a retrieval layer only after source ingestion, chunk metadata, access scopes and evaluation corpus are specified. Evaluate retrieval separately from answer generation.
- Add agent tools only with explicit allowlists, schema validation, least-privilege credentials, action-specific approvals and audit events.
- Add staged CI gates: fast deterministic tests on every PR; security/dependency scans and coverage gates; nightly load/soak and model evaluations; staging smoke tests before production.

## Important safety and deployment constraints

- Do not run an autonomous background loop in every Gunicorn worker. Use a dedicated worker/scheduler with a single-owner lease if autonomous jobs are introduced.
- Do not run multi-worker writes against the current JSON file and assume the process-local lock makes them safe.
- Never put provider API keys in the repository, test fixtures, logs or client-side code.
- Treat retrieved documents and model output as untrusted data. Validate tool arguments and enforce authorization outside the model.
- Report unsupported or untested surfaces honestly; a green unit-test run is not proof of production readiness.
