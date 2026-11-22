# Iskra AI — Unified Core

Iskra AI is a Polish-language knowledge-system project. This integration keeps its original twelve foundational pillars, graph-based knowledge model and autonomous learning concept while separating the code into a maintainable modular Flask monolith.

## Production entry point

Use the authenticated WSGI entry point:

```bash
gunicorn wsgi:app --workers 1 --timeout 120
```

- `/` — knowledge graph dashboard.
- `/api/network` — current graph snapshot.
- `/health` — public hosting health probe.

All routes except `/health` require `API_TOKEN`. Clients may send `Authorization: Bearer <API_TOKEN>` or `X-API-Token: <API_TOKEN>`. Browser Basic authentication is also supported; use the token as the password. If `API_TOKEN` is unset, non-health routes fail closed with HTTP 503. Do not expose `app:app` directly on a public network.

## Architecture

- `iskra/knowledge/graph.py` — twelve-pillar graph, validation, JSON persistence and POSIX file locking.
- `iskra/llm/router.py` — OpenAI-compatible, DeepSeek and Gemini provider routing with JSON-object validation and fallback.
- `iskra/api/routes.py` — injectable Flask API blueprint. API reads refresh the worker's graph snapshot from disk before responding.
- `iskra/config.py` — validated runtime configuration.
- `iskra/security/` and `security.py` — HTTP security headers and WSGI token authentication.
- `iskra/workers/autonomous.py` — opt-in autonomous graph-learning loop.
- `iskra/storage/sqlite.py` — isolated transactional SQLite adapter prototype; it is **not connected to the live graph path** and does not imply multi-tenant production support.
- `app.py` — compatibility façade preserving the existing Flask import and Render/Gunicorn integration.

## Data and deployment

The live graph currently remains in JSON at `$DATA_DIR/wiedza.json`. Writes use an atomic replace and a POSIX file lock; API reads reload the persisted snapshot so separate Gunicorn workers on the same filesystem see one another's updates.

This is suitable only for a single application instance using a shared local filesystem that supports POSIX locks. It is not a distributed multi-instance store. Render's ordinary container filesystem may be ephemeral; without a persistent disk, graph data can be lost on restart or redeploy. Back up `wiedza.json` before deployment changes. The SQLite adapter is a future migration option, not the current source of truth.

## LLM providers

Configure secrets in the hosting provider; never commit API keys.

- `LLM_PROVIDER`: `openai`, `deepseek`, or `gemini`.
- `LLM_FALLBACK_PROVIDERS`: comma-separated fallback order.
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`).
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default `deepseek-chat`).
- `GEMINI_API_KEY`, `GEMINI_MODEL` (both required to enable Gemini).

## Autonomous worker

The autonomous loop is disabled by default. It starts only when both `ENABLE_AUTONOMOUS_LOOP=true` and `ISKRA_PROCESS_ROLE=worker` are set. Never enable it in a Gunicorn web process. A dedicated managed worker service and singleton lease/lock are still required before enabling it in production; the current Render configuration intentionally leaves it disabled.

## Development and tests

```bash
python -m pip install -r requirements.txt
python -m compileall -q app.py iskra tests
python -m unittest discover -s tests -p "test_*.py" -v
```

GitHub Actions runs deterministic tests on Python 3.11 and 3.12 plus thread/process stress tests.

## Not production-ready as a multi-tenant SaaS

The project does not yet provide user accounts, tenant authorization, private document ingestion, tenant-filtered RAG, billing, PostgreSQL deployment or production observability. The SQLite prototype alone does not provide these controls. Do not upload confidential customer documents or expose this as a paid multi-tenant service until those capabilities are designed, implemented and tested.
