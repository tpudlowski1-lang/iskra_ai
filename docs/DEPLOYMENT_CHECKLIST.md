# Iskra AI — deployment checklist

This repository contains the application code. A successful GitHub merge is **not** proof that a live Render service has been configured or deployed.

## 1. Render service

Use these settings:

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn wsgi:app --workers 2 --threads 4 --timeout 120`
- Health check path: `/health`
- Do not start the public service with `python app.py` or `gunicorn app:app`; those bypass the WSGI authentication middleware.

## 2. Required environment variables

Set these in Render → service → Environment:

| Variable | Required | Purpose |
|---|---:|---|
| `API_TOKEN` | Yes | Administrator access to dashboard and admin API |
| `DATA_DIR` | Yes for durable data | Path to a persistent mounted disk |
| `LLM_PROVIDER` | Yes for generated answers | Primary provider: `openai`, `deepseek`, or `gemini` |
| Provider API key | Yes for selected model | For example `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` |
| `ENABLE_AUTONOMOUS_LOOP` | No | Keep `false` on multi-worker hosting |
| `ENABLE_SEMANTIC_SEARCH` | No | Defaults to `false`; vector embeddings are opt-in |
| `RATELIMIT_STORAGE_URI` | Recommended | Use shared Redis for consistent limits across workers |

Generate an administrator token in Termux or another trusted environment:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Paste the result into Render's secret environment variable `API_TOKEN`. Do not commit it to GitHub or paste it into a public issue/chat.

## 3. Persistent storage — do not skip

Set `DATA_DIR` to the mount path of a persistent disk. The application stores separate files:

- `iskra.sqlite3` — internal Iskra graph / 12 pillars;
- `wiedza.json` — compatibility mirror and graph recovery snapshot;
- `iskra_knowledge.sqlite3` — tenant records, API-key digests, company documents, chunks and embeddings.

The ordinary container filesystem may be ephemeral. Without a persistent disk, redeploys/restarts can lose the graph and company data. The Render Blueprint in this repository intentionally does not provision a paid disk automatically. Check the current Render plan and price before adding one.

Back up all three files regularly. Do not copy only the graph database and assume company documents are included.

## 4. Optional semantic search and privacy

By default, retrieval uses local SQLite FTS5. To enable semantic retrieval, set:

- `ENABLE_SEMANTIC_SEARCH=true`
- `OPENAI_API_KEY`
- optionally `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`

This sends document chunks during upload and questions during retrieval to OpenAI's embeddings API. Do not enable it for confidential/customer data until privacy, contractual and data-processing requirements have been reviewed. If embeddings are unavailable, FTS5 remains the fallback.

For shared rate limits across the two Gunicorn workers, configure a Redis service and set `RATELIMIT_STORAGE_URI` to its private connection URL. The default `memory://` backend is per process.

## 5. First-run verification

After Render reports the service as live:

1. `GET /health` returns HTTP 200.
2. `GET /workspace` returns the browser workspace shell.
3. `GET /api/network` without credentials returns HTTP 401.
4. `GET /admin/tenants` with `Authorization: Bearer <API_TOKEN>` returns HTTP 200.
5. Create a company using `POST /admin/tenants` with JSON `{"name":"Firma testowa"}`.
6. Save the returned tenant `api_key` securely; it is shown once and only its SHA-256 digest is stored.
7. Open `/workspace`, enter the tenant key, upload a non-sensitive test TXT file, and ask a question whose answer is present in that file.
8. Confirm the answer cites the source filename and that a second tenant cannot retrieve the first tenant's test text.

A ready-to-use browser workspace is available at `/workspace`. The tenant key is held in the current tab's `sessionStorage`; it is not placed in the URL.

## 6. Production boundary

This is a controlled pilot, not a finished multi-tenant SaaS. Named user accounts/roles, billing, private object storage, formal retention/export workflows, disaster-recovery drills, independent penetration testing and production monitoring remain outstanding. Do not onboard confidential customer data or charge customers until those controls are completed.
