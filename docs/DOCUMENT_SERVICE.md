# Iskra AI — modular document service (internal pilot foundation)

## Status

This branch adds bounded PDF/DOCX/TXT parsers, a private tenant-scoped SQLite repository and a Principal-bound service. **No document HTTP routes are registered.** The code is not available to customers and must not be treated as production-ready RAG.

The service is intentionally kept behind the application boundary until parsing can run in a resource-limited worker and the remaining operational controls are implemented.

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
- The repository uses composite tenant/document/chunk keys and a composite foreign key.
- FTS search joins on tenant ID, document ID and chunk ID, then filters by tenant ID.
- Document/chunk/FTS writes and deletes are transactional.
- Duplicate detection is scoped by tenant.
- The database directory is restricted to mode 0700 and database file to 0600; symlink database paths are rejected.
- Raw document contents and query text are not logged.

## Important limitations

- The parser runs synchronously in the caller process. It is not suitable for public upload endpoints until moved into a resource-limited worker with CPU, memory and wall-clock limits.
- PDF parsing is bounded by file, page and text limits and uses a current pypdf release, but those limits do not replace process isolation.
- There is no malware scanning/quarantine, private object storage, encryption-at-rest key management, retention scheduler, audit event pipeline or backup/restore procedure.
- SQLite is single-instance only; PostgreSQL document tables and RLS migration do not exist yet.
- FTS5 is lexical retrieval only. Retrieved content must be treated as untrusted data; no model prompt or answer generation is connected.
- The service is not wired into `app.py` or WSGI and has no public routes.

## Required next gates

1. Add a dedicated parser worker with process isolation and resource limits.
2. Add adversarial PDF/ZIP/XML fixtures, parser timeout and decompression tests.
3. Add PostgreSQL document/chunk schema, composite tenant keys and RLS.
4. Add malware scanning/quarantine strategy, audit events, quotas, retention and secure backup/restore.
5. Add route-level authorization and end-to-end cross-tenant read/search/delete tests.
6. Add retrieval evaluation, prompt-injection tests and citations before any generated answer.
7. Enable a feature flag only after independent review and staging validation.

Do not enable customer uploads or RAG until all gates pass.
