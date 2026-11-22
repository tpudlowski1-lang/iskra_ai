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
