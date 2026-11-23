# Iskra AI — modular document service (internal pilot foundation)

## Status

This branch adds bounded PDF/DOCX/TXT parsers, a private tenant-scoped SQLite repository and a Principal-bound service. **No document HTTP routes are registered.** The code is not available to customers and must not be treated as production-ready RAG.

The service is intentionally kept behind the application boundary. No HTTP routes are registered and no customer uploads are enabled. The default service parser now runs in a spawned, resource-limited process; the remaining operational controls and a stronger OS/container sandbox are still required.

## Current limits

- Upload bytes: 8 MiB.
- Extracted text: 1.5 million characters.
- PDF pages: 100; per-page extracted text: 100,000 characters.
- DOCX archive entries: 256; total declared uncompressed size: 12 MiB; XML part: 8 MiB; compression ratio: 100.
- Chunks: 1,000 characters with 150-character overlap; maximum 2,000 chunks.
- Supported formats: PDF, DOCX, TXT.
- PDF parsing uses pypdf 7.1.1; DOCX XML parsing uses defusedxml 0.7.1.
- Search is tenant-filtered lexical FTS5 and returns excerpts with source IDs. No embedding, reranker or generated answer is implemented.

## Security properties

- Every service method requires a verified `Principal`; system principal is rejected.
- Tenant scope is derived only from `Principal.tenant_id`, never from request data.
- The SQLite repository uses composite tenant/document/chunk keys and a composite foreign key.
- The PostgreSQL repository uses the same composite tenant keys/FK, generated `tsvector`, GIN index and RLS ENABLE + FORCE; every operation requires a verified Principal and transaction-local tenant scope.
- FTS search joins on tenant ID, document ID and chunk ID, then filters by tenant ID.
- Document/chunk/FTS writes and deletes are transactional.
- Duplicate detection is scoped by tenant.
- The database directory is restricted to mode 0700 and database file to 0600; symlink database paths are rejected.
- Raw document contents and query text are not logged.

## Important limitations

- The default parser runs in a spawned process with CPU, address-space, file-size, core-dump and file-descriptor limits and a parent-enforced wall-clock timeout. The child clears inherited environment variables before parsing and uses a restrictive umask. It returns JSON bytes (not a pickled Python object); the parent validates the schema, sanitized filename, extension and SHA-256 against the original input bytes.
- This is process/resource isolation, not a full OS sandbox: the child still runs under the same OS user, retains that user’s filesystem permissions, and has no seccomp/network namespace policy. Clearing environment variables is not network isolation and does not revoke inherited OS credentials. Do not expose public upload routes until a dedicated low-privilege worker/container boundary is reviewed.
- PDF parsing is bounded by file, page and text limits and uses a current pypdf release, but those limits do not replace process isolation.
- There is no malware scanning/quarantine, private object storage, encryption-at-rest key management, retention scheduler, audit event pipeline or backup/restore procedure.
- SQLite is single-instance only. A PostgreSQL document repository and migration `0002_tenant_documents.sql` are now available and integration-tested with a separate NOSUPERUSER/NOBYPASSRLS role; PostgreSQL remains opt-in.
- FTS5 is lexical retrieval only. Retrieved content must be treated as untrusted data; no model prompt or answer generation is connected.
- The service is not wired into `app.py` or WSGI and has no public routes.

## Required next gates

1. Add a dedicated low-privilege OS/container worker with no network access and enforce CPU/RAM/time quotas.
2. Extend adversarial PDF/ZIP/XML fixtures with process-kill, decompression and memory exhaustion cases.
3. Add PostgreSQL document/chunk schema, composite tenant keys and RLS.
4. Add malware scanning/quarantine strategy, audit events, quotas, retention and secure backup/restore.
5. Add route-level authorization and end-to-end cross-tenant read/search/delete tests.
6. Add retrieval evaluation, prompt-injection tests and citations before any generated answer.
7. Enable a feature flag only after independent review and staging validation.

Do not enable customer uploads or RAG until all gates pass.
