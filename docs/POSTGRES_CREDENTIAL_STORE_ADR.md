# ADR: PostgreSQL credential and browser-session store

Status: proposed implementation contract  
Scope: issue #96 and release blockers in issue #97  
Target branch: `refactor/modular-core`  
Safety: implementation must remain on a feature branch; no production deployment or customer data.

## 1. Decision

Implement a `PostgresCredentialStore` behind the behavior already exposed by `SQLiteCredentialStore`. Keep SQLite as a single-instance development/staging option. Select the backend explicitly with `ISKRA_CREDENTIAL_STORE_BACKEND=postgres` and require `ISKRA_CREDENTIAL_POSTGRES_DSN`; missing configuration, connection failure, or migration mismatch must fail closed. Do not fall back to `API_TOKEN` for browser-session exchange.

Do not silently reuse `ISKRA_POSTGRES_DSN` until the credential store has an explicitly reviewed database role and schema. Tenant graph/document storage and credential/session storage are separate security domains even if they share a PostgreSQL cluster.

## 2. Contract that must remain compatible

The current SQLite store exposes:
- `issue`, `authenticate`, `authenticate_with_metadata`;
- `create_browser_session`, `authenticate_browser_session`, `rotate_browser_session_csrf`, `revoke_browser_session`;
- `revoke`, `rotate`;
- tenant-scoped `list_for_tenant`, `issue_for_tenant`, `revoke_for_tenant`, `rotate_for_tenant`;
- `list_audit_events`.

The browser-session value returned to middleware currently contains a principal, credential ID, CSRF digest, raw CSRF token, and expiry. The raw CSRF token is the data-at-rest defect and must be removed from this contract. The replacement must expose only the digest and a freshly derived/issued token that is not read from the database.

## 3. PostgreSQL schema and storage rules

Create a new ordered migration (do not edit the existing tenant migrations) for:
- API credentials: opaque credential ID, unique SHA-256 bearer-token digest, subject, tenant ID, validated roles, creation/expiry/revocation timestamps.
- Browser sessions: SHA-256 session-token digest, credential foreign key, CSRF digest only, creation/expiry/revocation timestamps.
- Append-only credential audit events with actor, tenant, event type, credential ID, related credential ID, and timestamp.

Use PostgreSQL-native timestamp types consistently (prefer `TIMESTAMPTZ`), explicit constraints, foreign keys, and indexes. Never store raw API bearer tokens, browser session tokens, or raw CSRF tokens. Use parameterized psycopg queries only. Use `dict_row` or an equivalent mapping row factory; do not expose driver-specific row objects outside the adapter.

Use a bounded connection pool with explicit min/max sizes and health checks. Each operation must release its connection on every exit path. Mutating lifecycle operations must run in explicit transactions. Database errors must be translated to the existing safe `CredentialStoreUnavailable` error without returning SQL, DSNs, or secret material to HTTP responses.

## 4. Concurrency and tenant boundaries

- Credential rotation is one transaction: insert replacement, revoke old credential, append audit event; any failure rolls back all three.
- Revocation and rotation must immediately invalidate dependent browser sessions through an active-credential join, not by best-effort asynchronous cleanup.
- Last-active-admin checks must be concurrency-safe. Lock a tenant-scoped serialization key (or the tenant's credential guard row) before checking and mutating admin membership. A read-then-write check without a lock is not sufficient under PostgreSQL concurrency.
- Every tenant management query must include the authenticated tenant ID in the SQL predicate. A credential ID alone is never sufficient for tenant management.
- Never trust a tenant ID from request JSON or headers. Resolve tenant identity from the authenticated `Principal`.
- Test two independent app instances and two tenants against the same PostgreSQL database. Include concurrent attempts to revoke/demote the last two admins.

## 5. CSRF data minimization

Remove `csrf_token` from the `browser_sessions` table and from the persisted session model. Keep only `csrf_digest`.

Preserve the current multi-tab behavior: refreshing the assistant page must not invalidate a CSRF token already held by another tab. The implementation should derive a stable per-session CSRF token from the opaque session cookie using a dedicated server secret (HMAC-SHA-256), and compare its digest with the stored digest. The secret must be configured outside source control, must have sufficient entropy, and must fail closed when absent. Key rotation must have an explicit session invalidation procedure. Do not use the API bearer token or a general-purpose static admin token as the CSRF HMAC key.

Before adopting this design, test token derivation, session revocation, secret rotation, constant-time digest comparison, and multi-tab behavior. A raw CSRF value must never be logged or stored.

## 6. Migration and deployment

- Migration must be versioned, idempotent where practical, and run by a dedicated migration role.
- Runtime DB role must not be superuser, schema owner, or have privileges to alter schema.
- Startup must verify required migration versions; it must not auto-create a production schema using broad runtime privileges.
- Do not add production Render environment variables until PostgreSQL integration tests and staging evidence pass.
- Keep document ingestion and autonomous worker disabled.
- Do not enable multi-instance service until credential/session and tenant storage persistence are both configured and verified.

## 7. Required tests

1. Shared store contract tests for SQLite and PostgreSQL.
2. Raw token absence checks for credential, session, CSRF, and audit tables.
3. Credential issue/authenticate/expiry/revoke/rotate and audit atomicity.
4. Browser login, secure cookie, session expiry, logout, CSRF missing/mismatch/cross-origin rejection.
5. Multi-tab stable CSRF behavior and CSRF-secret rotation behavior.
6. Revocation and rotation invalidate sessions on a second app instance.
7. Tenant A cannot list, revoke, rotate, or infer Tenant B credentials.
8. Concurrent last-admin revoke/demotion cannot leave a tenant without an active admin.
9. Connection pool exhaustion, database outage, invalid schema, and migration failure fail closed.
10. PostgreSQL CI service job, migration checks, backup/restore rehearsal, and final commit workflow evidence.

## 8. Release gate

This ADR is a design record, not implementation or test evidence. Public SaaS/production and customer data remain blocked until issue #96 and issue #97 acceptance criteria pass, the final release SHA has green CI, a staging deployment produces recorded HTTP evidence, and an independent security review closes critical/high findings.
