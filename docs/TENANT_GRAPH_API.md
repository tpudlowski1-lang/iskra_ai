# Iskra AI — tenant-scoped graph API

## Endpoints

- `GET /api/tenant/network` — returns the authenticated tenant's graph. A new tenant is initialized with the twelve foundational Iskra pillars and their core connections.
- `PUT /api/tenant/network` — replaces the authenticated tenant's graph snapshot. The payload must retain all twelve foundational pillar IDs and the foundational connections.
- `GET /api/network` — legacy global graph, available only to the system administrator (`API_TOKEN`).
- `GET /health` — public health endpoint; it returns no tenant-specific data.

## Authentication and tenant scope

Send the tenant's API token as a bearer credential:

```http
Authorization: Bearer <tenant-api-token>
```

The WSGI middleware resolves the token to a server-managed principal. The API obtains the tenant scope from that principal only. Values such as `tenant_id` in the JSON body, URL query, or `X-Tenant-ID` header are ignored for authorization and storage selection.

## Example graph update

The request body must be JSON with `neurons` and `synapses`. Every foundational node and connection must remain present. Additional tenant-specific nodes and connections may be added.

```json
{
  "neurons": {
    "n_logika": {"label": "Logika", "weight": 1.0, "created": 1.0},
    "n_epistemologia": {"label": "Epistemologia", "weight": 1.0, "created": 1.0}
  },
  "synapses": [
    {"from": "n_logika", "to": "n_epistemologia", "strength": 0.95}
  ]
}
```

The abbreviated example above is illustrative only; a valid update must contain all twelve foundation nodes and all foundation edges. Requests are limited to 1 MiB.

## Storage

The API binds each `SQLiteGraphStore` instance to the authenticated tenant. By default the database file is `DATA_DIR/iskra_tenants.sqlite3`; set `ISKRA_TENANT_DB_PATH` to choose another path. SQLite uses tenant-scoped composite primary/foreign keys, transactional snapshot replacement, and private file permissions.

The graph and document stores walk every existing path component with `lstat`, reject symlinks/non-directories before creating descendants, create the final parent directory with mode `0700`, set the database file to `0600`, and open the database file with `O_NOFOLLOW` where the platform supports it. They also reject placing a database directly inside a shared sticky world-writable directory such as `/tmp`. These checks reduce accidental exposure and common symlink-path attacks; they do not eliminate TOCTOU races against a process able to mutate ancestor directories and are not a substitute for a private deployment data directory, filesystem ownership controls, or a hardened multi-process storage design. Do not allow untrusted local users to modify the storage directory.

This is an initial single-instance persistence layer. Do not deploy it for horizontally scaled production workloads or treat local ephemeral storage as durable. PostgreSQL, migration tooling, backup/restore drills, account lifecycle, credential revocation, and audit events are still required for production multi-tenant operation.
