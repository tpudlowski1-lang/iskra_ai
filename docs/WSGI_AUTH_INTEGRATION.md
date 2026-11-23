# Production WSGI authentication wiring

## Required entry point

Start public deployments with the WSGI module, for example:

```sh
gunicorn --bind 0.0.0.0:${PORT:-10000} wsgi:app
```

Do not use `app:app` for a public deployment: that imports the Flask application
without the authentication middleware installed by `wsgi.py`.

## Supported server-side configuration

- `API_TOKEN`: optional legacy system-administrator token.
- `ISKRA_API_CREDENTIALS_JSON`: optional static registry containing SHA-256 token digests and server-defined principals.
- `ISKRA_CREDENTIAL_DB_PATH`: optional path to the persistent SQLite credential registry.

The persistent registry is initialized by the WSGI factory and used for every
request. It supports issued, expiring, rotated and revoked credentials. Keep its
file on persistent storage, restrict filesystem access, and back it up securely.
Do not put raw bearer tokens or credential database contents in Git or logs.

The legacy `API_TOKEN` can coexist with the registry and maps only to the fixed
system administrator principal. Tenant identities must come from the registry;
never accept tenant IDs or roles from request headers, query parameters or JSON.

## Health and failure behavior

- `/health` remains public for platform health checks.
- If no authentication mechanism is configured, non-health requests return
  `503 service_not_configured`.
- Invalid static credential configuration fails closed with HTTP 503.
- Invalid, expired or revoked credentials return HTTP 401.
- Credential database failures return HTTP 503; the middleware does not fall
  back to a different tenant identity when the registry is unavailable.

## Deployment limitations

The SQLite credential store is intended for a single application instance with
a persistent writable disk. Do not share it across multiple replicas or use an
ephemeral filesystem. Use a properly provisioned shared database backend before
scaling horizontally. A passing CI test proves application wiring and local
SQLite behavior, not the host's secret, disk, TLS or backup configuration.


## Credential resolution order

When multiple server-side mechanisms are configured, the middleware checks the persistent SQLite registry first, then the legacy system-admin token, then the static SHA-256 digest registry. A persistent-registry miss may fall through to the other configured mechanisms. A persistent-registry exception returns HTTP 503 and does **not** fall through, so an unavailable identity store cannot silently change the authentication source. A non-Principal object returned by a credential backend is rejected.
