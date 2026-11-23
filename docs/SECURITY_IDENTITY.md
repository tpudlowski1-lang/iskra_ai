# Iskra AI — identity and authorization baseline

**Status:** implemented foundation; not a multi-user or multi-tenant release.

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

## Explicit limitations

This is not yet named-user authentication or tenant isolation:

- one shared administrator token is still the only configured credential;
- there is no user/token registry, revocation, expiry, rotation, or provisioning workflow;
- no member credentials are issued;
- the live graph remains a shared JSON file and has no tenant partition;
- the SQLite tenant-scoped adapter is still disconnected from the live application;
- PostgreSQL, migrations, audit events, and per-tenant authorization are not implemented.

The fixed `system` tenant value is a trusted server-side placeholder, not a customer tenant. Never accept tenant identity from request input. Do not enable customer uploads, tenant APIs, or RAG until credential-to-principal mapping, storage scoping, and adversarial cross-tenant tests are implemented.

## Verification

The request-principal branch passed the unified GitHub Actions workflow on commit `78b5ad76645184775e6fbfca2c32aee01a25138d`:

- Python 3.11: 58 tests passed;
- Python 3.12: 58 tests passed;
- Python compilation: passed;
- pinned dependency audit: passed.

Workflow: https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45086753649

A green unit/CI run is not a production-readiness or tenant-isolation certification.
