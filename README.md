# Iskra AI — Unified Core

Iskra AI is an experimental Polish-language knowledge-system project. The canonical integration is a modular Flask monolith that preserves the original twelve foundational pillars, graph-based knowledge model, provider fallback behavior and existing HTTP contracts.

## Current development program

All restructuring streams are coordinated in one source of truth:

- [Unified restructuring program](docs/UNIFIED_RESTRUCTURING_PROGRAM.md)
- [Modular core design](docs/superpowers/specs/2026-11-23-modular-core-design.md)
- [Implementation plan](docs/superpowers/plans/2026-11-23-modular-core.md)
- [Production readiness checklist](docs/PRODUCTION_READINESS.md)
- [Data migration policy](docs/DATA_MIGRATION.md)

The canonical integration branch is `refactor/modular-core`. Historical branches are reference material; their code is ported selectively after review, not merged wholesale.

## Application entry points and security

- `app.py` — compatibility entry point for Flask and existing imports.
- `wsgi.py` — production WSGI entry point; wraps the Flask app with fail-closed API-token authentication from `security.py`.
- `/` — knowledge graph dashboard.
- `/api/network` — graph snapshot.
- `/health` — public hosting health probe.

Every route except `/health` requires the shared `API_TOKEN`. Clients may send `Authorization: Bearer <API_TOKEN>`, `X-API-Token: <API_TOKEN>`, or HTTP Basic authentication with the token as the password. If `API_TOKEN` is unset, non-health routes fail closed with HTTP 503. Use `wsgi:app` for public deployment; do not expose `app:app` directly because that bypasses the WSGI authentication wrapper.

This is only a shared administrator token, not a full identity system. Named user accounts, roles, tenant-specific credentials, request-scoped tenant authorization and application-wide resource ownership are not yet implemented. Do not expose customer documents or treat this as a production multi-tenant SaaS.

## Architecture

- `iskra/config.py` — validated runtime configuration.
- `iskra/knowledge/graph.py` — graph model, twelve foundational pillars and JSON persistence.
- `iskra/llm/router.py` — OpenAI-compatible, DeepSeek and Gemini provider routing with JSON-object validation and fallback.
- `iskra/api/routes.py` — injectable Flask API blueprint.
- `iskra/security/headers.py` — baseline response security headers.
- `security.py` — shared API-token WSGI middleware.
- `iskra/workers/autonomous.py` — opt-in autonomous graph-learning loop.
- `iskra/storage/protocols.py` — storage interface.
- `iskra/storage/sqlite.py` — tenant-scoped transactional SQLite adapter prototype; it is **not connected to the live Flask graph path** and is not production tenant isolation.

## Data and deployment

The live graph currently remains in JSON at `$DATA_DIR/wiedza.json`. Writes use atomic replacement and a POSIX file lock. API reads refresh the worker's graph snapshot from disk so workers sharing the same filesystem can see updates.

This is not a distributed multi-instance store. Hosting filesystems may be ephemeral; without persistent storage, data can be lost on restart or redeploy. Back up `wiedza.json` before deployment changes. PostgreSQL is the target for concurrent, multi-tenant production use; it has not yet been implemented.

## LLM providers

The optional autonomous worker currently sends the complete legacy global knowledge graph in its prompt to the configured external provider. It is disabled by default and must remain disabled until data classification, provider terms, retention and privacy controls are reviewed. Do not place customer or confidential data in the global graph. See [LLM provider data handling](docs/LLM_PROVIDER_DATA_HANDLING.md).


Configure credentials only in hosting secrets/environment settings; never commit API keys.

- `LLM_PROVIDER`: `openai`, `deepseek`, or `gemini`.
- `LLM_FALLBACK_PROVIDERS`: comma-separated fallback order.
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`).
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default `deepseek-chat`).
- `GEMINI_API_KEY`, `GEMINI_MODEL` (both required to enable Gemini).

## Autonomous work

The autonomous loop is disabled by default. Do not enable it in a Gunicorn web process: each worker could start its own loop. A dedicated worker, singleton lease, idempotency and safe shutdown are still required before production use.

## Development and tests

```bash
python -m pip install -r requirements.txt
python -m compileall -q app.py iskra tests
python -m unittest discover -s tests -p "test_*.py" -v
```

GitHub Actions runs deterministic tests on Python 3.11 and 3.12 and a concurrency stress suite.

## Not production-ready as a multi-tenant SaaS

The shared API token protects the WSGI entry point, but the project does not yet provide named user accounts, role-based authorization, tenant isolation, private document ingestion, tenant-filtered RAG, billing, PostgreSQL deployment or production observability. The SQLite adapter alone does not provide these controls. Do not upload confidential customer documents or expose this as a paid multi-tenant service until the required controls are implemented and tested.
