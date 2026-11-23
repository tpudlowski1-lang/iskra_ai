# Iskra AI — Modular Core Design

## Intent
Evolve the experimental Flask application into a maintainable modular monolith while preserving the Polish knowledge graph, its twelve foundational pillars, provider fallback behavior, existing HTTP routes, and the existing test suite.

## Goals
- Preserve backward compatibility for `/`, `/api/network`, and `/health`.
- Separate domain logic, configuration, providers, persistence, API, and security into modules incrementally.
- Eliminate unsafe DOM rendering and establish secure HTTP defaults.
- Keep autonomous background work disabled by default.
- Establish CI gates for every refactor commit and retain concurrency regression tests.
- Prepare, but do not falsely claim to have completed, tenant isolation, PostgreSQL persistence, document ingestion, RAG, authentication, and billing.

## Non-goals for this phase
- No migration to microservices or FastAPI.
- No payment processing or public customer onboarding.
- No enabling autonomous execution in Gunicorn workers.
- No production multi-tenancy until authorization and storage isolation are implemented and tested.

## Approaches
1. Modular Flask monolith — selected. Lowest migration risk; retains the existing hosting contract and permits staged extraction.
2. FastAPI migration — deferred because it adds framework migration risk without solving the immediate persistence and security gaps.
3. Microservices — rejected for now because they increase operational and hosting complexity before independent scaling needs exist.

## Architecture decisions
- Keep `app.py` as a compatibility entry point for the existing Render start command.
- Extract configuration, knowledge graph, LLM routing, API, security, and workers into focused packages in separate, reviewable steps.
- Preserve the legacy JSON graph format during the first extraction; add a repository interface before database migration.
- Use SQLite for local deterministic tests and PostgreSQL for eventual multi-process/multi-tenant deployments.
- Treat model output and stored labels as untrusted input. Render text via DOM `textContent`, never HTML interpolation.
- Keep provider credentials in hosting secrets only.
- Keep autonomous jobs disabled by default; later use a single-owner worker/lease rather than per-Gunicorn-worker threads.

## Constraints
- Python 3.11 baseline and existing Flask/Gunicorn deployment remain supported.
- The user operates primarily from Android; changes must be reviewable and manageable through GitHub.
- Keep hosting and dependency costs low; do not add services without a demonstrated need.
- Do not overwrite `main`, `commercial-mvp`, or existing quality/stress branches.
- A green unit suite is not proof of production readiness.

## Acceptance criteria
- Existing route contracts and twelve graph pillars remain intact.
- Existing deterministic and concurrency tests pass in CI.
- Dashboard data is rendered without `innerHTML`.
- Security headers are present and covered by tests.
- CI runs on `refactor/modular-core`.
- Remaining production blockers are explicitly documented.
