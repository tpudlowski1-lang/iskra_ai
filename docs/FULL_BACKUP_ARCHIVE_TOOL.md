# Full backup archive utility

This document describes the draft implementation in `scripts/backup_iskra_data.py`.

## Scope

The utility accepts an explicit allowlist of named resources. It does not recursively scan directories and does not discover or include secrets. SQLite resources are snapshotted with SQLite's online backup API. JSON resources are copied and parsed. The archive contains a manifest with SHA-256 checksums, and restore validates every included resource before publishing a new directory.

Optional resources may be explicitly absent. Missing required resources abort archive creation. Restore refuses to overwrite an existing target directory.

## Create an archive

Stop application writes and background workers first. The caller must confirm this with `--writes-paused`.

Example syntax:

`python -m scripts.backup_iskra_data create --writes-paused --archive /secure-backups/iskra.zip --json data/wiedza.json=/srv/iskra/wiedza.json --sqlite data/tenants.sqlite3=/srv/iskra/iskra_tenants.sqlite3`

Repeat `--sqlite NAME=PATH` for each active SQLite store. Repeat `--json NAME=PATH` for additional JSON stores.

## Restore to a new staging directory

`python -m scripts.backup_iskra_data restore --archive /secure-backups/iskra.zip --target /srv/iskra-restore-staging`

## Limitations

The example paths do not assert which resources are active on a particular host. Operators must inspect actual deployment settings and list only active stores; an active required resource must not be omitted. The tool cannot stop external processes or guarantee a single transaction across independent databases. For a common point in time, writes and workers must be quiesced before invocation.

PostgreSQL, object storage, and hosting secrets require separate provider-native backup and recovery procedures. This archive does not handle them. Production backup/restore has not been performed by this code change.

## Integrity and authenticity

The SHA-256 values detect accidental corruption and verify that restored bytes match the manifest. They do not authenticate who created the archive: an attacker able to replace both the archive and its manifest can recompute the hashes. For production, store archives in access-controlled, encrypted backup storage and add a separately managed signature or HMAC key; never place that key in the archive. This utility does not implement archive signing or encryption.


## Memory and authenticity limits

JSON resources are capped at 64 MiB because Python's standard JSON parser materializes the document in memory. SQLite snapshots and archive members have separate larger limits; an archive-wide size limit does not make unbounded JSON parsing safe.

The manifest SHA-256 values detect accidental corruption and mismatch between a manifest and an extracted resource. They do **not** authenticate the archive: an attacker able to replace the archive can replace both a resource and its manifest hash. Treat the archive as sensitive, store it in access-controlled encrypted backup storage, and use an independently managed digital signature or authenticated envelope when protection against malicious replacement is required. Do not store signing keys beside the archive.
