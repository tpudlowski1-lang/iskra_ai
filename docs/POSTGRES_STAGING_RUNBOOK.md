# PostgreSQL staging cutover and rollback runbook

**Status:** operator procedure for a future staging rehearsal only. No production cutover is authorized or implied.

## Scope and non-goals

This procedure migrates the tenant-scoped SQLite graph database (`iskra_tenants.sqlite3`) into the PostgreSQL tenant graph tables. It does **not** migrate the legacy global knowledge graph (`wiedza.json`), credentials, document SQLite data, model state, logs, uploads or other application files. Document storage remains a separate migration and release gate. A successful graph migration does not make the whole application PostgreSQL-backed.

Never rehearse against production customer data until a data-processing basis, access approval, encrypted backup destination and operator are established. Use synthetic staging tenants first.

## Identities and secrets

Use three distinct database identities:

1. **Schema migration owner:** applies `migrations/0001_tenant_graph.sql` and `migrations/0002_tenant_documents.sql`. Keep its credential out of the web service.
2. **Migration operator role:** separate credential for the data migration rehearsal. It needs only the target graph table privileges required by the script, must be `NOSUPERUSER NOBYPASSRLS`, and must not own the tables. It operates one tenant at a time through transaction-local `iskra.tenant_id`. Do not grant it DDL or superuser privileges.
3. **Application runtime role:** dedicated `NOSUPERUSER NOBYPASSRLS`, not table owner, with only required application DML permissions.

Store each DSN in a secret manager or protected environment variable. Do not place passwords in Git, logs, command history or process arguments. The migration utility resolves the target in this order: explicit `--postgres-dsn`, `ISKRA_POSTGRES_MIGRATION_DSN`, then `ISKRA_POSTGRES_DSN`. It deliberately does not infer a target from generic `DATABASE_URL`.

## Staging preflight

- [ ] Create a disposable PostgreSQL staging database and private backup destination.
- [ ] Record the exact application commit, migration file checksums, PostgreSQL version and staging change window.
- [ ] Confirm no customer data is present; use synthetic tenant fixtures.
- [ ] Stop all writers to the source tenant SQLite database, including background/autonomous workers.
- [ ] Verify the application is not using the legacy global JSON graph as if it were tenant storage.
- [ ] Create the schema with the schema migration identity, applying migrations in order: `0001_tenant_graph.sql`, then `0002_tenant_documents.sql`.
- [ ] Create separate migration and runtime roles. Verify both have `rolsuper=false`, `rolbypassrls=false`; verify neither owns tenant tables.
- [ ] Grant only schema USAGE and required DML on the graph tables to the migration/runtime roles.
- [ ] Confirm the target is empty for every staging tenant and that cross-tenant RLS tests pass.

Example verification query (run as a database operator; do not expose credential values):

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN ('iskra_app', 'iskra_migrator');

SELECT c.relname, r.rolname AS owner, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_roles r ON r.oid = c.relowner
WHERE c.relname IN (
  'iskra_graph_neurons', 'iskra_graph_synapses',
  'iskra_tenant_documents', 'iskra_tenant_document_chunks'
);
```

Expected: both roles are non-superuser and non-BYPASSRLS; the application and migration roles do not own the tables; RLS and FORCE RLS are true.

## Backup and dry run

Run from a protected operator environment with a local copy of the tenant SQLite database:

```bash
umask 077
export ISKRA_POSTGRES_MIGRATION_DSN='(load from secret manager; do not paste into shell history)'
python -m scripts.migrate_tenant_sqlite_to_postgres \
  --source /secure/input/iskra_tenants.sqlite3 \
  --backup-dir /secure/iskra-backups
```

The placeholder above is explanatory; inject the secret through the platform's secret manager, not as a literal shell command. The default invocation is a dry run. It creates a consistent SQLite online backup, a SHA-256 checksum and a private manifest, validates all tenant graphs, and prints tenant/node/edge counts. Review the report and compare the source tenant inventory with the expected staging fixture list.

Preserve the backup, checksum and manifest in encrypted, access-controlled storage. A SHA-256 checksum detects accidental corruption; it does not authenticate the backup against a malicious replacement. Use signed/encrypted backup envelopes and independent key management for production.

## Apply to staging

Only after the preflight and dry-run report are approved:

```bash
python -m scripts.migrate_tenant_sqlite_to_postgres \
  --source /secure/input/iskra_tenants.sqlite3 \
  --backup-dir /secure/iskra-backups \
  --apply
```

The migration runs all tenant graph writes in one PostgreSQL transaction, refuses existing target tenants by default, reads each tenant back and compares the semantic snapshot before commit. Do not use `--replace-existing` for a normal first migration. That flag is destructive and requires a separately approved test case.

## Staging acceptance tests

- [ ] The migration report says `committed_and_verified` and counts match the approved dry-run report.
- [ ] Every synthetic tenant reads back the exact expected graph snapshot.
- [ ] Tenant A cannot read, modify or delete Tenant B data; repeat for graph reads and writes.
- [ ] Missing tenant context returns no rows and rejects writes under the runtime role.
- [ ] A forged tenant ID from HTTP/request data cannot change the authenticated Principal's scope.
- [ ] Runtime role cannot disable/alter RLS, create tables, or read as table owner.
- [ ] Application restart/redeploy does not lose PostgreSQL data.
- [ ] A database backup is restored into a separate empty staging database; verify row counts and semantic snapshots.
- [ ] Rollback is rehearsed and recorded, including measured recovery time and data-loss window.
- [ ] The legacy `wiedza.json` graph is backed up and remains on its separately documented storage path.

Do not switch the staging application to PostgreSQL until every applicable item passes and the change owner signs the evidence record. Configure `ISKRA_TENANT_STORAGE_BACKEND=postgres` and `ISKRA_POSTGRES_DSN` only in the staging service. Keep document backend on SQLite unless its separate migration and acceptance plan has been completed.

## Rollback

1. Stop staging writes and disable background workers.
2. Revert the staging service's tenant graph backend setting to `sqlite`.
3. Restore the pre-cutover tenant SQLite backup to a new private path; validate checksum, SQLite integrity and tenant snapshot counts before switching the setting.
4. Restart the previous application configuration and run authenticated tenant smoke tests.
5. Keep the PostgreSQL staging database read-only for investigation; do not delete it until evidence is retained.
6. Record the rollback reason, operator, timestamps, affected tenant IDs, observed data-loss window and follow-up actions.

Never overwrite the only source backup or run `--replace-existing` as an improvised rollback. Production rollback requires an independently tested recovery plan.

## Evidence record template

For each rehearsal, record: operator/approver, date/time and timezone, application commit, migration checksums, PostgreSQL version, source backup checksum, tenant/node/edge counts, role verification output, test results, restore result, rollback result, measured recovery time, deviations and final go/no-go decision.

## Current gate

The code and PostgreSQL 16 CI integration tests provide a tested migration mechanism. They do not prove a real staging rehearsal, durable backups, live deployment, operational recovery, or production readiness. This checklist must be completed with evidence before a staging cutover can be marked successful.
