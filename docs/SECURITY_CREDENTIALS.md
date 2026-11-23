# Iskra AI — credentials and authorization boundary

## Server-side credential registry

The WSGI middleware accepts two credential classes:

1. `API_TOKEN` — the legacy system administrator credential. It resolves to the fixed `system` tenant and `admin` role.
2. `ISKRA_API_CREDENTIALS_JSON` — a JSON array of per-user/per-tenant credentials. Each entry stores only a SHA-256 digest of the raw API token and a server-defined principal.

Example (use a newly generated digest and never commit a real token):

```json
[
  {
    "token_sha256": "<64-character-lowercase-sha256>",
    "subject": "user-17",
    "tenant_id": "tenant-a",
    "roles": ["member"]
  }
]
```

Use a high-entropy random token (not a human-chosen password). Generate and hash it locally; never store it in the repository:

```sh
python -c "import secrets,hashlib; t=secrets.token_urlsafe(32); print('TOKEN='+t); print('SHA256='+hashlib.sha256(t.encode()).hexdigest())"
```

Set the JSON as a protected environment variable in the deployment platform. Keep the raw token with its intended user. Rotate a credential by replacing its digest in the server-side configuration. Malformed credential configuration fails closed with HTTP 503; unknown credentials receive HTTP 401.

## Authorization rules

- The middleware derives the principal only after validating a server-side credential.
- `tenant_id` supplied in a URL, query string, body, or request header is never trusted.
- The legacy global `/api/network` endpoint requires both the `admin` role and the `system` tenant scope; a tenant administrator cannot read it.
- `/health` remains public and does not receive an authenticated principal.
- The existing dashboard shell contains no tenant data; its graph API call is administrator-only.

## Important current limitation

This registry is a static credential bootstrap, not a complete user-management system. It does not yet provide user invitation, password reset, session lifecycle, token revocation without deployment configuration changes, audit events, PostgreSQL persistence, or tenant-scoped graph/document storage. A `member` principal is authenticated but intentionally cannot read or mutate the legacy global graph.

Do not add tenant data endpoints until storage queries enforce the authenticated principal's tenant scope and negative cross-tenant read/write/delete tests pass. The document/RAG prototype remains experimental and is not enabled by this change.
