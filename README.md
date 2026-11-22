# Iskra AI

Iskra AI is an experimental Polish-language assistant project. The commercial product direction is a private knowledge assistant for small businesses: answers grounded in company documents, draft replies and offers, and clear source references.

## Current branch

- `main`: original experimental knowledge-graph dashboard.
- `commercial-mvp`: product plan, technical audit, configurable LLM provider router, and safer background-loop default.

The `commercial-mvp` branch is work in progress and has not yet been verified in a live Render deployment.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY="..."
python app.py
```

The current application exposes:
- `/` — knowledge graph dashboard
- `/api/network` — current graph data
- `/health` — health check

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

## Important limitations

This branch is not yet a multi-tenant SaaS. It does not yet provide customer accounts, document upload, tenant-isolated retrieval, billing, or production-grade persistence. Do not upload customer confidential documents or expose it as a paid customer service until those controls are implemented and tested.
