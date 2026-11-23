# Tenant account and credential lifecycle (draft)

## Scope

Draft PR #82 adds API operations for a tenant administrator to manage API credentials within the administrator's authenticated tenant. Draft PR #84 is the rebased candidate for a minimal tenant-admin console inside /assistant for listing, issuing, rotating and revoking credentials. It does not add public signup, password authentication, account recovery, email verification or billing.

## Prerequisites

- Deploy through `wsgi:app`, not directly through Flask's `app:app`.
- Configure a durable private `ISKRA_CREDENTIAL_DB_PATH` and protect/backup it.
- The persistent credential registry must be available; otherwise these routes return 503.
- The request Principal must come from verified server-side credentials. Tenant ID is never accepted from the request.

## API

All routes require a tenant administrator role:

- `GET /api/tenant/credentials` — list credential metadata for the current tenant. No raw tokens or token digests are returned.
- `POST /api/tenant/credentials` — issue a new credential. JSON accepts `subject`, optional `roles` (defaults to member) and optional `expires_at`. Tenant ID is derived from Principal and any extra fields (including tenant_id) are rejected.
- `POST /api/tenant/credentials/{credential_id}/rotate` — atomically issue a replacement and revoke the old credential. Roles may be retained or reduced, never increased.
- `DELETE /api/tenant/credentials/{credential_id}` — revoke a credential only if it belongs to the current tenant.

Issuance defaults to a 90-day expiry and tenant admins cannot request more than 365 days. Rotation preserves an existing expiry, caps legacy long-lived credentials at 365 days, and gives non-expiring legacy credentials a new 90-day lifetime. Issuance/rotation returns a high-entropy token once. Store it immediately in a secret manager; it cannot be retrieved later. Audit events record actor, subject, tenant and operation, but never the token or digest.

## Security properties

- Every operation requires a server-derived Principal with admin role and a non-system tenant.
- List, revoke and rotate queries are tenant-filtered in SQL, not merely filtered in the UI.
- Cross-tenant credential IDs return not-found and do not mutate the other tenant.
- A member cannot manage credentials.
- The fixed system administrator identity cannot use tenant account endpoints.
- Token digests remain the only persisted token representation.

## Limitations and production gates

- Static API-token lifecycle only; no password login, MFA, self-service recovery, invitation emails, signup or billing.
- Draft PR #84 contains a minimal browser admin console in `/assistant`; it is not yet independently reviewed or production-ready.
- SQLite credential store is single-instance; use a reviewed PostgreSQL backend before horizontal scaling.
- No customer-visible audit log retention/export, alerting, operator separation of duties or secure token delivery workflow.
- A tenant administrator is trusted to issue/revoke that tenant's own credentials; the system does not independently verify the identity represented by the supplied subject label.
- Staging deployment, backup/restore drill, abuse/rate-limit review and external security assessment remain required.

This is a draft technical control, not evidence of production readiness or legal compliance.
