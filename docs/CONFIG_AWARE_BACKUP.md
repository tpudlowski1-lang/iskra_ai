# Configuration-aware backup inventory

## Purpose

The backup utility now has a configuration-derived inventory mode. It uses the same validated `iskra.config.load_settings()` function as the Flask application and resolves only known Iskra data locations. It does not recursively scan `DATA_DIR`, inspect arbitrary files, or include secrets.

## Inspect the active backup plan

```bash
python -m scripts.backup_iskra_data plan
```

The plan lists:
- legacy knowledge graph JSON: `DATA_DIR/wiedza.json` (required);
- tenant graph SQLite: `ISKRA_TENANT_DB_PATH` or `DATA_DIR/iskra_tenants.sqlite3` when tenant backend is SQLite;
- document repository SQLite: `DATA_DIR/private_documents/documents.sqlite3` when document backend is SQLite;
- credential registry SQLite: `ISKRA_CREDENTIAL_DB_PATH` only when explicitly configured.

Tenant and document SQLite stores are marked optional because their repositories initialize lazily. Their absent status is still recorded in the archive manifest. A configured credential registry is required because WSGI initializes it at startup.

## Create from the validated configuration

First stop all web processes, autonomous workers, schedulers and any other process that can write to these stores. Then run:

```bash
python -m scripts.backup_iskra_data create --from-config --writes-paused --archive /secure-backups/iskra.zip
```

The explicit `--writes-paused` flag is an operator attestation, not an automated process lock. The utility cannot stop processes or guarantee one transaction across separate stores.

## PostgreSQL is a hard stop, not a silent omission

If either `ISKRA_TENANT_STORAGE_BACKEND=postgres` or `ISKRA_DOCUMENT_STORAGE_BACKEND=postgres` is active, `plan` reports the corresponding remote store as an external requirement. `create --from-config` refuses to claim a complete backup until the PostgreSQL backup has been performed and verified separately using provider-native tooling (for example, `pg_dump` plus a restore drill). The DSN itself is never printed or archived.

## Explicit exclusions

- Environment variables, API tokens, provider keys, DSNs and other secrets.
- Original upload files/object storage: the repository does not currently expose a confirmed object-storage adapter or configured root path.
- PostgreSQL data: requires a separate native backup and verified restore.
- Render filesystem durability: not inferred from repository configuration; hosting disk and retention must be checked independently.

## Operational boundary

A successful local archive is not a complete system recovery proof. Before production use, operators must validate the external PostgreSQL and object-storage recovery paths, encrypt and access-control the backup destination, protect archive authenticity with an independently managed signature/HMAC, and perform a restore drill in isolated staging.
