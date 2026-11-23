# Iskra AI

Iskra AI is an experimental Polish-language assistant project. The commercial product direction is a private knowledge assistant for small businesses: answers grounded in company documents, draft replies and offers, and clear source references.

## Active engineering branches

- `main`: original experimental knowledge-graph dashboard.
- `iskra-full-quality-gates`: persistence and quality/stress-test work.
- `iskra-unified-integrated`: integrated application, SQLite persistence, WSGI token middleware and security tests.
- `iskra-integration-hardening`: controlled continuation branch based on `iskra-unified-integrated`; CI triggers and integration status are maintained here.

The integration branches have diverged. Do not merge them blindly; review file-level differences and run CI first.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY="..."
export API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
gunicorn wsgi:app
```

The production WSGI entry point is `wsgi:app`. It wraps Flask with token authentication. The `/health` endpoint remains public for hosting health checks; every other path requires authentication.

Authentication methods:
- `Authorization: Bearer <API_TOKEN>` for API clients;
- `X-API-Token: <API_TOKEN>` for API clients;
- HTTP Basic authentication for browser access (any username; use API_TOKEN as the password).

If `API_TOKEN` is missing, the middleware fails closed with HTTP 503 on all non-health routes. Never use the development entry point `app:app` as a public production server because it bypasses the WSGI authentication wrapper.

## Storage and migration

The graph store uses SQLite as its durable source of truth:
- database: `$DATA_DIR/iskra.sqlite3`;
- compatibility/export snapshot: `$DATA_DIR/wiedza.json`;
- SQLite uses WAL journaling, a 30-second busy timeout and transactional writes;
- on first start, an existing valid `wiedza.json` is imported automatically;
- the JSON snapshot is retained for inspection, export and recovery if the SQLite database is damaged.

Set `DATA_DIR` to a persistent writable directory on the hosting platform. A container's ordinary filesystem may be ephemeral: without a persistent disk, data can be lost on redeploy/restart. Do not point multiple independent hosts at a local SQLite file; horizontal multi-instance production should move to PostgreSQL.

Before upgrading, take a copy of both `iskra.sqlite3` and `wiedza.json`. Keep the autonomous learning loop disabled during migration and deployment.

## LLM configuration

Set keys only in the hosting provider's secret/environment settings. Never commit API keys.

- `LLM_PROVIDER`: primary provider: `openai`, `deepseek`, or `gemini`.
- `LLM_FALLBACK_PROVIDERS`: comma-separated fallback order.
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default model: `gpt-4o-mini`).
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default model: `deepseek-chat`).
- `GEMINI_API_KEY`, `GEMINI_MODEL` (both required to enable Gemini).

The autonomous graph-learning loop is disabled by default. Set `ENABLE_AUTONOMOUS_LOOP=true` only for a controlled single-process experiment. Do not enable it with multiple Gunicorn workers: each worker would start its own loop.

## Product and engineering documents

- [Commercial MVP plan](docs/PRODUCT_PLAN.md)
- [Technical audit](docs/TECHNICAL_AUDIT.md)
- [Unified Core integration status](docs/INTEGRATION_STATUS.md)

## Important limitations

This branch is not yet a multi-tenant SaaS. It does not yet provide customer accounts, tenant-isolated retrieval, billing, or production-grade document storage. Do not upload customer confidential documents or expose it as a paid customer service until those controls are implemented and tested.
