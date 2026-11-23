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
- requires the parent directory to be owned by the service user and inaccessible to group/other users (0700); opens the directory and database with `O_NOFOLLOW`, checks regular-file ownership/link count, and applies database permissions through the file descriptor (0600);
- closes database connections deterministically.

Issuance, revocation and rotation are recorded in a separate audit table in the same SQLite transaction as the credential change. Rotation atomically revokes the old token and issues a replacement; it preserves subject/tenant and may only retain or reduce roles. Audit records contain no raw token or token digest. This is a local SQLite operator audit trail, not an immutable centralized audit service; file access, encrypted backups, retention and external monitoring still require operational controls.

The local operator CLI is `python -m scripts.manage_credentials` with `issue`, `rotate`, `revoke` and `audit` subcommands. Mutating commands require `--confirm`; issuing an `admin` role also requires `--allow-admin`. Draft PR #88 carries the rebased tenant-scoped API and minimal browser admin console: tenant admins can issue/list/rotate/revoke only credentials bound to their own Principal tenant. New tokens are returned once; list responses contain metadata only. These routes require the persistent SQLite registry and are not yet integrated into the canonical release candidate. Operators must store newly issued tokens in a secret manager immediately.

## Configuration

Set `ISKRA_CREDENTIAL_DB_PATH` to a durable, private filesystem path, for example `/var/lib/iskra/credentials.sqlite3`. The directory must be writable only by the service account and included in encrypted backups. Do not use ephemeral storage for a production credential registry.

If the variable is absent, SQLite registry authentication is not activated. If configured but the database cannot be initialized securely, WSGI startup fails rather than silently disabling authentication.

## Limitations and production gates

- SQLite is a single-instance backend; it is not suitable for multiple web workers/replicas sharing network storage. PostgreSQL is required before horizontal scaling.
- No public signup, password login, account recovery, email verification, billing or complete customer account lifecycle exists. Draft PR #88 includes tenant-admin issue/list/rotate/revoke endpoints and a minimal admin console; it still requires canonical integration, staging security review, and a full customer account lifecycle before it can be considered a managed account product.
- No automatic cleanup of expired records exists; expiry is enforced at authentication.
- Database encryption at rest, backup restore drills, operator identity verification, secret delivery and incident/key lifecycle procedures remain outstanding.
- The global compatibility graph remains on legacy JSON and is system-admin-only. The tenant API is connected to the principal-bound SQLite tenant graph store; PostgreSQL is an opt-in backend.
- A principal carrying a tenant ID does not by itself guarantee tenant data isolation. The new `TenantGraphStoreFactory` binds a `SQLiteGraphStore` to the verified `Principal` and rejects missing/untyped principals and the system principal. Domain services should obtain tenant stores only through this factory; never construct a tenant store from request parameters. This factory is a storage boundary prototype, not yet connected to live Flask graph routes.
- Customer document uploads and RAG remain disabled until cross-tenant read/write/delete tests, PostgreSQL migration rehearsal, authorization coverage and restore drills pass.

## Verification

The branch adds unit and WSGI integration tests for token digest-only persistence, expiry, revocation, atomic rotation, privilege non-escalation, audit redaction, operator CLI confirmation, tenant spoofing, backend failure, legacy admin compatibility, public health behavior, principal-bound store construction and cross-tenant read/write isolation. CI results must be reported only after GitHub Actions completes on the exact branch head.


## Reserved system-administrator identity

Global system routes require the exact fixed `SYSTEM_ADMIN` principal installed by the legacy system-administrator credential. A tenant-scoped principal with the string tenant ID `system` and role `admin` is not sufficient. The static tenant credential registry and persistent SQLite tenant credential issuer reject the reserved `system` tenant. This prevents an accidentally or incorrectly provisioned tenant credential from inheriting global-administrator access. Tenant admins remain scoped to their own tenant. Authentication also rejects pre-existing persistent credential rows whose stored `tenant_id` is `system`; operators must revoke such legacy rows and use only the fixed `API_TOKEN` identity for system administration.
