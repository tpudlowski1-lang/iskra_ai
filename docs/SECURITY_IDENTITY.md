# Iskra AI — identity and authorization baseline

**Status:** trusted request-principal and credential middleware integration implemented; production WSGI still uses the legacy shared token only. Not a multi-tenant data release.

## Request identity

The production entry point is `wsgi:app`. `ApiTokenMiddleware` supports the legacy shared `API_TOKEN` and an injected credential-store backend. A verified registry token resolves to an immutable `Principal` whose subject, tenant ID and roles come only from the server-side credential record. Client query, body and header values cannot replace this identity.

Unknown/revoked/expired tokens are rejected. Credential backend failures return HTTP 503 rather than silently degrading authentication. The public `/health` probe bypasses authentication and receives no principal.

The current `wsgi.py` does not instantiate or inject the credential store, so the active production credential remains the legacy `API_TOKEN`. Directly exposing `app:app` bypasses the WSGI middleware and is not supported for public deployments.

## Credential registry

`iskra.security.credentials.SQLiteCredentialStore`:

- issues high-entropy random bearer tokens and returns plaintext only once;
- stores SHA-256 digests, never raw bearer tokens;
- binds subject, tenant ID and roles to server-side records;
- supports optional expiry and explicit revocation;
- fails closed for unknown, expired, revoked, malformed or corrupt records;
- uses owner-only database-file permissions (`0600`).

SQLite remains a single-instance prototype, not a high-availability credential service. Operational provisioning, account recovery, audit events, key lifecycle, PostgreSQL and backup/restore drills remain future gates.

## Authorization and global graph boundary

`require_roles` provides role-based checks based only on the trusted principal. `require_system_admin` additionally requires the fixed `system` tenant.

The legacy `/api/network` endpoint returns one global JSON graph. It is restricted to the `admin` role AND tenant ID `system`. Members and tenant-scoped administrators receive HTTP 403; requests without a principal receive 401. This endpoint is not a tenant API and must not be exposed to tenant-scoped identities.

## Explicit limitations

- No public endpoint, CLI or administrator UI for issuing credentials.
- The SQLite credential store is not enabled by `wsgi.py` and is not an HA secret-management service.
- The live graph remains a shared JSON file without tenant partitioning.
- The tenant-scoped SQLite graph adapter is not yet wired into the live application.
- PostgreSQL, migrations, audit events, full per-tenant graph authorization, private document ingestion and tenant-filtered RAG remain future work.
- Do not enable customer uploads, tenant APIs or RAG for customer data.

## Verification

The credential middleware integration passed GitHub Actions on its tested merge HEAD: Python 3.11 and 3.12 each passed 74 tests, compilation passed, and the dependency audit passed. The follow-up global-graph authorization and connection-lifecycle changes require a fresh CI run on their exact HEAD before acceptance.
