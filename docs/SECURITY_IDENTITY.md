# Iskra AI — identity and authorization baseline

**Status:** credential middleware and system-only global graph authorization implemented; production WSGI still uses the legacy shared token only. Not a multi-tenant data release.

## Request identity

The production entry point is `wsgi:app`. `ApiTokenMiddleware` accepts the legacy shared `API_TOKEN` and an injected credential-store backend. A verified registry token resolves to an immutable `Principal` whose subject, tenant ID and roles come only from the server-side credential record. Client query, body and header values cannot replace this identity.

Unknown, expired or revoked credentials are rejected. Credential backend failures return HTTP 503 rather than silently degrading authentication. The public `/health` probe bypasses authentication and receives no principal.

The current `wsgi.py` does not instantiate or inject the credential store, so the active production credential remains the legacy `API_TOKEN`. Directly exposing `app:app` bypasses the WSGI middleware and is not supported for public deployments.

## Credential registry

`iskra.security.credentials.SQLiteCredentialStore` issues high-entropy random bearer tokens, returns plaintext only once, stores only SHA-256 digests, binds subject/tenant/roles server-side, supports expiry and revocation, and fails closed for invalid records. Its database file is restricted to owner-only permissions. All credential operations use a context manager that closes SQLite connections deterministically.

SQLite remains a single-instance prototype, not a high-availability credential service. Operational provisioning, account recovery, audit events, key lifecycle, PostgreSQL and backup/restore drills remain future gates.

## Authorization and global graph boundary

`require_roles` provides role checks based only on the trusted principal. `require_system_admin` additionally requires the fixed `system` tenant.

The legacy `/api/network` endpoint returns one global JSON graph. It is restricted to the `admin` role AND tenant ID `system`. Members and tenant-scoped administrators receive HTTP 403; requests without a principal receive 401. This endpoint is not a tenant API and must not be exposed to tenant-scoped identities.

## Explicit limitations

- No public endpoint, CLI or administrator UI for issuing credentials.
- The credential store is injectable but not enabled by `wsgi.py`; the live deployment remains on `API_TOKEN`.
- SQLite is not an HA secret-management service.
- The live graph remains a shared JSON file without tenant partitioning.
- The tenant-scoped SQLite graph adapter is not yet wired into the live application.
- PostgreSQL, migrations, audit events, full per-tenant graph authorization, private document ingestion and tenant-filtered RAG remain future work.
- Do not enable customer uploads, tenant APIs or RAG for customer data.

## Verification

The prior credential-middleware and credential-store lifecycle stages passed GitHub Actions on their tested heads (74 and 75 tests respectively on Python 3.11/3.12). This PR adds system-only graph authorization and corresponding tests; a fresh CI run on the exact final HEAD is required before acceptance.
