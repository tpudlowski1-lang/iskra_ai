# Iskra AI

Iskra AI is an experimental Polish-language assistant project. The commercial product direction is a private knowledge assistant for small businesses: answers grounded in company documents, draft replies and offers, and clear source references.

## Current branch

- `main`: original experimental knowledge-graph dashboard.
- `commercial-mvp`: product plan, technical audit, configurable LLM provider router, SQLite graph persistence, and security hardening in progress.

The `commercial-mvp` branch is work in progress and has not yet been verified in a live Render deployment.

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
- graph database: `$DATA_DIR/iskra.sqlite3`;
- tenant document database: `$DATA_DIR/iskra_knowledge.sqlite3`;
- compatibility/export snapshot: `$DATA_DIR/wiedza.json`;
- SQLite uses WAL journaling, a 30-second busy timeout and transactional writes;
- on first start, an existing valid `wiedza.json` is imported automatically;
- the JSON snapshot is retained for inspection, export and recovery if the SQLite database is damaged.

Set `DATA_DIR` to a persistent writable directory on the hosting platform. A container's ordinary filesystem may be ephemeral: without a persistent disk, data can be lost on redeploy/restart. Do not point multiple independent hosts at a local SQLite file; horizontal multi-instance production should move to PostgreSQL.

Before upgrading, take a copy of `iskra.sqlite3`, `iskra_knowledge.sqlite3`, and `wiedza.json`. The graph and company-document databases are separate so recovery of the internal graph does not overwrite tenant records. Keep the autonomous learning loop disabled during migration and deployment.

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

This branch now contains a tenant-isolated document pilot API with per-company API keys, PDF/DOCX/TXT ingestion and tenant-filtered SQLite FTS5 search. It is not yet a complete multi-tenant SaaS: named user accounts, roles, semantic vector retrieval, generated grounded answers, billing, private object storage, formal retention controls and production operations are still missing. Do not upload highly sensitive customer documents or sell the service until those remaining controls are implemented and independently reviewed.


## Tenant document knowledge (pilot API)

The authenticated administrator creates a company workspace:

```http
POST /admin/tenants
Authorization: Bearer <API_TOKEN>
Content-Type: application/json

{"name":"Firma testowa"}
```

The response includes a one-time `api_key`. Store it securely; only its SHA-256 digest is persisted. Tenant API keys can access only:
- `GET /api/documents`
- `POST /api/documents` with multipart field `file`
- `DELETE /api/documents/<document_id>`
- `POST /api/search` with JSON `{"query":"...","limit":5}`; `POST /api/chat` with JSON `{"question":"..."}` for grounded answers and citations

Send the tenant key in `X-Iskra-Tenant-Key`. Tenant identity is derived from the validated key, never from a client-supplied tenant ID. Document records, chunks, retrieval, and deletion are scoped to that tenant in SQLite. Supported uploads: PDF, DOCX and TXT; maximum upload 8 MB, extracted text 1.5 million characters, 200 PDF pages. Search returns source excerpts. Optional semantic retrieval uses OpenAI embeddings when ENABLE_SEMANTIC_SEARCH=true and OPENAI_API_KEY is configured; it is disabled by default to avoid surprise API costs. Without embeddings, the system uses SQLite FTS5 lexical retrieval. The chat endpoint uses the configured LLM router with system-level rules that treat document text as untrusted input, validates source IDs in citations, and refuses to guess when no source matches. Retrieval currently uses tenant-filtered SQLite FTS5 (lexical search), not vector embeddings.

This is a controlled pilot foundation, not a complete SaaS identity system: it does not yet include named user accounts, roles, billing, object storage, or formal retention controls. Administrators can rotate tenant keys or delete tenant data through the admin API. Protect tenant keys as passwords and use HTTPS.
