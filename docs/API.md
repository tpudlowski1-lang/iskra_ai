# Iskra AI API

All production routes except `/health` and the empty `/workspace` HTML shell are protected by `wsgi.py`.

## Administrator

Send `Authorization: Bearer <API_TOKEN>` or HTTP Basic with `API_TOKEN` as the password.

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/tenants` | List tenant IDs and names |
| POST | `/admin/tenants` | Create a tenant; returns its one-time API key |
| POST | `/admin/tenants/{tenant_id}/rotate-key` | Revoke the old key and return a new key |
| DELETE | `/admin/tenants/{tenant_id}` | Delete the tenant and its documents |

Create a tenant:

```bash
curl -X POST "$BASE_URL/admin/tenants" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Firma testowa"}'
```

Store the returned `api_key` securely. The server stores only its SHA-256 digest.

## Tenant

Send `X-Iskra-Tenant-Key: <tenant_api_key>`. The server derives the tenant ID from the validated key; never send a tenant ID in the request body.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/documents` | List this tenant's documents |
| POST | `/api/documents` | Upload multipart field `file` (PDF/DOCX/TXT, max 8 MB) |
| DELETE | `/api/documents/{document_id}` | Delete only this tenant's document |
| POST | `/api/search` | Retrieve source excerpts |
| POST | `/api/chat` | Grounded answer with validated citations |

Upload a file:

```bash
curl -X POST "$BASE_URL/api/documents" \
  -H "X-Iskra-Tenant-Key: $TENANT_KEY" \
  -F "file=@regulamin.txt"
```

Search:

```bash
curl -X POST "$BASE_URL/api/search" \
  -H "X-Iskra-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"termin zwrotu","limit":5}'
```

Ask a grounded question:

```bash
curl -X POST "$BASE_URL/api/chat" \
  -H "X-Iskra-Tenant-Key: $TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"Jaki jest termin zwrotu?"}'
```

The chat response includes `answer`, `citations`, `sources` and `grounded`. Citation IDs are validated against retrieved source IDs. When retrieval finds no evidence, the model is not called and the response explicitly says that the documents do not contain an answer.

## Limits and errors

- Chat: 15 requests/minute per tenant.
- Search: 60 requests/minute per tenant.
- Document operations: 20 requests/minute per tenant.
- Tenant creation: 30 requests/minute per administrator/IP.
- Key rotation/deletion: 10 requests/minute per administrator/IP.
- Upload limit: 8 MB; extracted text limit: 1.5 million characters; PDF limit: 200 pages.

Common statuses: 400 invalid request, 401 missing/invalid key, 403 wrong role, 413 upload too large, 429 rate limit exceeded, 502 invalid model output/citations, 503 provider unavailable or service not configured.
