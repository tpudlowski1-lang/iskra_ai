# Iskra AI — identity and authorization baseline

**Status:** multi-principal API-token foundation implemented; not yet a multi-tenant data release. This branch is validated only after its own required CI checks complete.

## Trusted request identity

The production entry point is `wsgi:app`. The WSGI middleware validates credentials and attaches an immutable `Principal` to the WSGI environment only after successful authentication.

Supported credential sources:

- `API_TOKEN_REGISTRY`: JSON object mapping lowercase SHA-256 token digests to server-owned principal definitions;
- `API_TOKEN`: legacy shared administrator token retained for backward compatibility.

Registry shape (the digest below is illustrative, not a usable credential):

```json
{
  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
    "subject": "user-123",
    "tenant_id": "tenant-123",
    "roles": ["member"]
  }
}
```

Generate a digest from a strong random token during provisioning with Python's `hashlib.sha256(token.encode("utf-8")).hexdigest()`. Store only the digest in `API_TOKEN_REGISTRY`; deliver the raw token once through a secret manager. Never commit raw credentials or real digests to Git.

The registry is validated at application startup. Invalid JSON, malformed digests, unknown fields, invalid principal values, or unsupported roles stop startup instead of silently weakening authentication. Authentication compares token digests and never logs the supplied token.

## Rotation and revocation

- Rotation: issue a new random token, add its digest, deploy, then remove the old digest.
- Revocation: remove the digest and redeploy/restart the application.
- Multiple active credentials can coexist during a controlled rotation.
- This implementation does not yet provide expiry, self-service issuance, refresh tokens, account recovery, or a database-backed audit trail.
- The legacy `API_TOKEN` still grants the single system administrator principal. Remove it only after migration and compatibility checks are complete.

## Authorization and current data boundary

`iskra.security.policy.require_roles` reads only the trusted principal. Client-provided tenant IDs, role headers, URL parameters, and JSON fields cannot replace it.

The current `/api/network` endpoint returns the single global legacy graph. It is therefore restricted to the `admin` role AND the fixed `system` tenant. Both ordinary members and tenant-scoped administrators receive HTTP 403. This is an important safety boundary, not tenant-aware graph isolation.

The public `/health` probe remains unauthenticated and does not receive a principal. Use `wsgi:app`; direct `app:app` bypasses the middleware.

## Explicit limitations

- The legacy JSON graph is still global and has no tenant partition.
- The SQLite tenant-scoped adapter remains disconnected from the live application.
- There is no PostgreSQL persistence, migration/rollback, tenant-aware service layer, or cross-tenant storage test against the live API.
- No account lifecycle, password login, expiry, refresh, or audit event pipeline exists.
- Do not enable customer uploads, tenant APIs, or RAG until storage scoping and adversarial isolation tests are implemented.

## Verification

The request-principal baseline passed CI on commit `4a269579449f4f2397db7bfeef1e8a51b749439c`. The token-registry branch adds tests for hashed token lookup, invalid registry configuration, server-derived tenant identity, role enforcement on the global graph, and public health. Its status must be judged from the CI run attached to its exact HEAD; a prior green run does not verify later commits.
