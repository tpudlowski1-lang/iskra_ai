# PostgreSQL credential and browser-session store design

**Status:** design gate; implementation not yet approved.  
**Scope:** replace the single-instance SQLite credential/session registry used by wsgi.py with a PostgreSQL implementation that preserves the existing SQLiteCredentialStore contract. This is not a production migration or a claim of readiness.

## Why this is the next persistence blocker

Tenant graph and document repositories already have PostgreSQL adapters, but wsgi.py still constructs SQLiteCredentialStore from ISKRA_CREDENTIAL_DB_PATH. That SQLite registry stores API credential digests, browser-session digests, CSRF digests/tokens and credential audit events. Moving graph/documents to PostgreSQL alone does not make a multi-instance deployment safe: browser authentication and revocation would remain tied to one local SQLite file.

## Compatibility contract

The PostgreSQL adapter must expose the same public operations and return shapes as the SQLite implementation:

- issue, authenticate_with_metadata, authenticate
- create_browser_session, authenticate_browser_session, rotate_browser_session_csrf, revoke_browser_session
- revoke, rotate
- list_for_tenant, issue_for_tenant, revoke_for_tenant, rotate_for_tenant
- list_audit_events

Keep IssuedCredential, BrowserSession, CredentialStoreUnavailable and LastTenantAdminError behavior compatible. WSGI middleware must depend on a small store interface, not SQLite-specific SQL or connection objects. SQLite remains supported for local development and single-instance deployments.

## Data model

Use a dedicated iskra_auth schema and migration version separate from tenant graph/document migrations. Tables:

1. api_credentials: credential ID, unique SHA-256 token digest, subject, tenant ID, normalized roles, created/expiry/revocation timestamps.
2. browser_sessions: unique SHA-256 session digest, credential ID FK, CSRF digest, CSRF token only if required by the current middleware contract, created/expiry/revocation timestamps.
3. credential_audit_events: immutable event ID/type, credential and related credential IDs, subject, tenant, actor and event timestamp.

Persist only high-entropy token digests; never persist bearer/session plaintext. Use constraints for role and event-type validation, foreign keys, unique digests, expiry ordering where practical, and indexes for digest lookup, tenant listing, active-admin checks, session-to-credential lookup and audit chronology. All mutations and their audit event must commit atomically.

## Authentication lookup boundary — mandatory security design

Authentication begins with an opaque token digest, before a trusted tenant Principal exists. A naive tenant RLS policy cannot safely scope this first lookup. Do not solve this by trusting a tenant ID supplied in HTTP headers, cookies or request JSON, and do not grant the ordinary application role unrestricted table access.

Before implementation, choose and independently review one of these explicit patterns:

- Preferred candidate: narrowly scoped database authentication functions. Expose fixed-purpose functions for credential-digest lookup and browser-session-digest lookup. Use hardened SECURITY DEFINER functions with a fixed safe search_path, schema-qualified object references, no dynamic SQL, minimal returned columns, strict input validation, a dedicated non-login owner with only minimum read privileges, and EXECUTE grants only to the runtime role. Assess interaction of FORCE ROW LEVEL SECURITY with the function owner; do not silently grant broad BYPASSRLS privileges. If a narrowly privileged function owner must bypass RLS for this lookup, document the exact privilege boundary and test that it cannot mutate or enumerate records through any other interface.
- Alternative: isolated authentication service/role. A separate process/connection identity performs digest lookup and returns only verified principal metadata. Its network access, credentials, audit and blast radius must be documented; tenant-admin writes remain tenant-scoped.

The design must make it impossible for a web request to select its own tenant. Every tenant-admin mutation must derive tenant scope from the verified Principal and enforce it in SQL and, where applicable, RLS.

## Transaction and concurrency rules

- Use parameterized SQL only.
- Use transaction-local context (set_config(..., true)) for tenant-scoped operations; never session-global tenant state on pooled connections.
- Lock the relevant tenant credential set when checking the last-active-admin invariant, so concurrent revocations/rotations cannot remove the final admin.
- Credential rotation/revocation and associated browser-session invalidation must be atomic.
- Session creation must verify the credential is active, unexpired and belongs to the exact Principal in the same transaction.
- CSRF rotation, logout and session revocation must be race-safe and idempotent where the SQLite contract currently is.
- Database errors must fail closed and map to the existing safe store-unavailable error; never log DSNs, tokens, digests or CSRF material.

## Configuration and rollout

Introduce an explicit setting such as ISKRA_CREDENTIAL_STORAGE_BACKEND=sqlite|postgres. Preserve the current SQLite default for development. PostgreSQL mode must require the existing ISKRA_POSTGRES_DSN or a separately named credential-store DSN if separation of privileges requires it. Never silently fall back from PostgreSQL to SQLite after a connection or schema error.

A staging cutover must:
1. Use synthetic tenants and a disposable PostgreSQL database.
2. Apply a reviewed migration with a separate schema owner.
3. Provision runtime/function roles with verified least privilege.
4. Run full credential, browser-session, CSRF, expiry, rotation, logout, audit and tenant-admin concurrency suites against PostgreSQL.
5. Prove cross-tenant denial and that absent tenant context returns no tenant data.
6. Rehearse credential/session migration or deliberately require credential re-issuance; never copy plaintext tokens (they are not available).
7. Restart and run multiple app workers, proving revocation is immediately visible across workers.
8. Back up, restore to a separate database, verify records and audit history, and rehearse rollback.
9. Switch only staging to PostgreSQL; production remains unchanged until separate approval.

## Required tests before merge

- Contract parity against SQLite adapter for every public method and return shape.
- Invalid, expired and revoked bearer credentials rejected.
- Session invalidated on credential expiry, rotation and revocation.
- Session digest and CSRF material never exposed in responses/logs.
- Cross-tenant list/issue/revoke/rotate attempts denied.
- Last active tenant admin cannot be removed, including concurrent requests.
- Authentication functions cannot enumerate or mutate credentials; only intended fields are returned.
- SQL injection inputs remain data, not SQL.
- Transaction rollback leaves no orphan audit/session/credential records.
- Multiple worker processes observe revocation and CSRF rotation.
- PostgreSQL outage fails closed without falling back to local SQLite.

## Non-goals

This work does not add signup, email verification, MFA, password recovery, billing, customer-facing self-service credential management, or production deployment. Those remain separate release gates.
