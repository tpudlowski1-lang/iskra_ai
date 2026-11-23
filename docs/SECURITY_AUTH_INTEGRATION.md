# Integrated authentication stack — validation scope

This branch combines the WSGI authentication integration, the fail-closed direct development entrypoint, and the reserved system-administrator identity boundary.

## Credential resolution

1. A configured persistent SQLite credential registry is checked first.
2. The fixed legacy `API_TOKEN` maps only to the singleton `SYSTEM_ADMIN`.
3. A miss in the persistent registry may resolve against the static SHA-256 digest registry.
4. An exception from the persistent registry returns 503 and never falls through to another identity source.
5. Unconfigured or malformed server-side credentials fail closed.

The development entrypoint and public production WSGI entrypoint use the same authentication middleware. The global graph API accepts only the exact `SYSTEM_ADMIN` object. Tenant-scoped static or SQLite credentials cannot claim the reserved `system` tenant. Authentication rejects legacy persistent rows already stored with `tenant_id=system`, so an old row cannot retain system-like access after upgrade.

## Integrated tests required

- Python 3.11 and 3.12 complete unittest discovery.
- Dependency vulnerability audit.
- WSGI public health and fail-closed private routes.
- Static and persistent credential coexistence.
- Credential store outage does not fall back to another credential source.
- Forged `Principal(subject, tenant_id="system", roles={"admin"})` is denied global access.
- Tenant credential issuance rejects the reserved system tenant.
- Development `python app.py` wrapper does not mutate the global Flask WSGI application.

## Boundaries

A successful CI run is application-level evidence only. It does not verify production secret provisioning, persistent volume durability, TLS termination, external network controls, legal compliance or production deployment. Draft integration branch; no merge or deployment.
