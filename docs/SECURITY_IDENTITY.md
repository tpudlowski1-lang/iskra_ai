# Iskra AI — security identity and credential storage

**Status:** persistent credential backend implemented behind an opt-in WSGI setting. This is not yet a complete account-management system or a production multi-tenant certification.

## Authentication flow

The production entry point is `wsgi:app`. If `ISKRA_CREDENTIAL_DB_PATH` is configured, WSGI creates a `SQLiteCredentialStore` and injects it into `ApiTokenMiddleware`. Otherwise, the existing shared `API_TOKEN` and static hashed `ISKRA_API_CREDENTIALS_JSON` configuration remain available.

The middleware derives `Principal(subject, tenant_id, roles)` only from a verified credential. Request body, query parameters and caller-supplied tenant headers are never identity sources. The public `/health` route remains unauthenticated.

When the SQLite store is configured:
- valid registry tokens resolve to the server-bound principal;
- revoked, expired or unknown registry tokens are rejected;
- credential database errors return 503 and never fall back to an unauthenticated request;
- the legacy shared `API_TOKEN` remains an explicit compatibility administrator credential;
- the static JSON credential map is not consulted for non-legacy tokens while the database store is active.

## SQLite credential registry

`iskra.security.sqlite_credentials.SQLiteCredentialStore`:
- generates 384-bit URL-safe bearer tokens;
- persists only SHA-256 token digests, not plaintext tokens;
- binds subject, tenant ID and roles to the credential record;
- supports optional expiry and immediate revocation;
- rejects malformed and oversized tokens;
- uses parameterized SQL and transactional writes;
- sets database file permissions to owner-only (0600);
- closes database connections deterministically.

A newly issued token is returned once by `issue()`. The caller is responsible for delivering it securely; it must not be logged or committed to source control. There is no public issuance endpoint in this change.

## Configuration

Set `ISKRA_CREDENTIAL_DB_PATH` to a durable, private filesystem path, for example `/var/lib/iskra/credentials.sqlite3`. The directory must be writable only by the service account and included in encrypted backups. Do not use ephemeral storage for a production credential registry.

If the variable is absent, SQLite registry authentication is not activated. If configured but the database cannot be initialized securely, WSGI startup fails rather than silently disabling authentication.

## Limitations and production gates

- SQLite is a single-instance backend; it is not suitable for multiple web workers/replicas sharing network storage. PostgreSQL is required before horizontal scaling.
- No account provisioning API, password login, self-service token rotation, recovery workflow or audit-event pipeline exists.
- No automatic cleanup of expired records exists; expiry is enforced at authentication.
- Database encryption at rest, backup restore drills, migration tooling and operator key lifecycle procedures remain outstanding.
- The legacy `/api/network` endpoint exposes the shared JSON graph only to the fixed system administrator. Customer graph operations use the tenant-scoped SQLite API; tenant storage is selected from the verified `Principal`, never from a request-supplied tenant ID. The system principal is explicitly rejected by the customer tenant-store factory.
- A principal carrying a tenant ID does not by itself guarantee tenant data isolation. The new `TenantGraphStoreFactory` binds a `SQLiteGraphStore` to the verified `Principal` and rejects missing/untyped principals and the system principal. Domain services should obtain tenant stores only through this factory; never construct a tenant store from request parameters. This factory is a storage boundary prototype, not yet connected to live Flask graph routes.
- Customer uploads, tenant APIs and RAG must remain disabled until cross-tenant read/write/delete tests, PostgreSQL migrations, authorization coverage and restore drills pass.

## Verification

The branch adds unit and WSGI integration tests for issuance, token digest-only persistence, expiry, revocation, tenant spoofing, backend failure, untyped principal rejection, legacy admin compatibility, public health behavior, principal-bound store construction and cross-tenant read/write isolation. CI results must be reported only after GitHub Actions completes on the exact branch head.
