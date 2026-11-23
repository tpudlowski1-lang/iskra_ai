# Iskra AI — identity and authorization baseline

**Status:** trusted request-principal foundation implemented; credential registry prototype under review. Not a multi-user or multi-tenant release.

## Request identity

The production entry point is `wsgi:app`. Its `ApiTokenMiddleware` validates the configured shared `API_TOKEN` and, only after successful validation, attaches an immutable `Principal` to the WSGI environment under the private application key.

The current compatibility mapping is:

- subject: `api-token-admin`
- tenant: `system`
- roles: `admin`

The public `/health` probe bypasses authentication and receives no principal. Every other path is protected by the WSGI middleware. Do not expose `app:app` directly in a public deployment because it bypasses that middleware.

## Authorization primitives

`iskra.security.policy.require_roles` provides a deny-by-default decorator for routes that need role-specific checks. It reads only the trusted principal attached by the authentication layer. A query parameter, URL segment, JSON body, or ordinary request header cannot create or replace a principal.

Existing routes retain their compatibility behavior. The role decorator is a foundation for new protected endpoints; it is not a claim that a complete account/role policy has already been applied to every domain operation.

## Credential registry prototype

`iskra.security.credentials.SQLiteCredentialStore` introduces a persistence contract and a single-instance SQLite prototype:

- issues high-entropy random bearer tokens and returns plaintext only once;
- stores SHA-256 token digests, never the raw bearer token;
- binds subject, tenant ID and roles to the server-side credential record;
- supports optional expiry and explicit revocation;
- fails closed for unknown, expired, revoked, malformed or corrupt records;
- creates the database file with owner-only permissions (`0600`).

The WSGI middleware now accepts an injected credential store and resolves a registry token to its server-bound principal. Store failures return 503 (fail closed); revoked/unknown tokens return 401. The production `wsgi.py` entry point does not yet instantiate or inject the store, so the current shared `API_TOKEN` remains the only active credential. There is no public token-issuance endpoint and no user provisioning workflow. SQLite is a single-instance prototype, not a high-availability credential service; PostgreSQL and operational key management remain future work. The registry and middleware integration must not be treated as production-ready until migration, concurrency, backup/restore, permission, key lifecycle and security review gates pass.

## Explicit limitations

This is not yet named-user authentication or tenant isolation:

- one shared administrator token is still the only credential accepted by the live WSGI application;
- the credential registry is not connected to request authentication;
- there is no account lifecycle, password authentication, self-service provisioning, rotation workflow or administrator recovery process;
- the live graph remains a shared JSON file and has no tenant partition;
- the tenant-scoped SQLite graph adapter is disconnected from the live application;
- PostgreSQL, migrations, audit events, and per-tenant authorization are not implemented.

The fixed `system` tenant value is a trusted server-side placeholder, not a customer tenant. Never accept tenant identity from request input. Do not enable customer uploads, tenant APIs, or RAG until credential-to-principal mapping, storage scoping, and adversarial cross-tenant tests are implemented.

## Verification

The request-principal branch passed the unified GitHub Actions workflow on commit `4a269579449f4f2397db7bfeef1e8a51b749439c`:

- Python 3.11: 58 tests passed;
- Python 3.12: 58 tests passed;
- Python compilation: passed;
- pinned dependency audit: passed.

Workflow: https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45086904528

The credential registry branch adds focused unit tests; their status must be taken from CI on the exact branch HEAD. A green unit/CI run is not a production-readiness or tenant-isolation certification.
