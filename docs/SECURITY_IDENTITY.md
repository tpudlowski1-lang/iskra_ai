# Iskra AI — identity and authorization baseline

**Status:** credential-store authentication is integrated behind explicit configuration; not a production multi-tenant release.

## Request identity

The production entry point is `wsgi:app`. WSGI middleware accepts:

- the legacy `API_TOKEN`, mapped to the single system administrator principal for compatibility;
- credentials verified by `SQLiteCredentialStore` when `CREDENTIAL_DB_PATH` points to a persistent credential database.

The credential store persists only SHA-256 digests of high-entropy random tokens. The raw token is returned only once by the internal issuance method. It supports server-owned subject/tenant/role mapping, optional expiry, and revocation. Authentication attaches the resulting immutable `Principal` to the WSGI environment only after verification.

If `CREDENTIAL_DB_PATH` is unset, the SQLite credential store is not activated. If the database is configured but unavailable, authentication fails closed with HTTP 503. Unknown, expired and revoked credentials are rejected. The public `/health` probe remains unauthenticated and receives no principal.

## Provisioning and operational limits

There is not yet a public endpoint, CLI or administrator UI for issuing credentials. Provisioning is an internal application operation using `SQLiteCredentialStore.issue(principal, expires_at=...)`; never add raw tokens to Git, logs, analytics or ordinary support tickets. Store the returned token once in an appropriate secret manager and securely deliver it to its owner.

Revocation uses `SQLiteCredentialStore.revoke(credential_id)`. The credential ID is an identifier, not an authentication secret. Database backups contain token digests and principal metadata; protect them as sensitive security data.

SQLite is a single-instance prototype. Do not place it on an unreliable shared network filesystem or assume it provides multi-instance HA. PostgreSQL, transactional migration, backup/restore drills, audit events, expiry policy, key rotation workflow and operational provisioning are still required.

## Authorization and global graph boundary

`iskra.security.policy.require_roles` provides role checks based only on the trusted principal. `require_system_admin` additionally requires the fixed `system` tenant.

The legacy `/api/network` endpoint returns one global JSON graph and is restricted to the system administrator. Tenant-scoped administrators and members receive HTTP 403. The endpoint is not a tenant API. Do not remove this restriction until the live graph service is tenant-aware and cross-tenant read/write/delete tests pass.

Use `wsgi:app`; direct `app:app` bypasses the WSGI authentication middleware.

## Explicit limitations

- No public account registration, token issuance, account recovery or administrator UI exists.
- SQLite credentials are not a high-availability or production secret-management service.
- The live knowledge graph remains a shared JSON file with no tenant partition.
- The tenant-scoped SQLite graph adapter is not yet connected to the live API.
- PostgreSQL, migrations, audit events, per-tenant graph authorization, private document ingestion and tenant-filtered RAG remain future work.
- Do not enable customer uploads, tenant APIs or RAG for customer data.

## Verification

The credential-store prototype passed its own GitHub Actions run on its then-tested merge HEAD: Python 3.11 and 3.12 each passed 67 tests, compilation passed, and the dependency audit passed. This follow-up integrates credential lookup into WSGI and adds system-only authorization; it must pass fresh CI on its exact HEAD before it can be considered verified.
