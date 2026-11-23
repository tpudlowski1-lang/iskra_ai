# Iskra AI — document ingestion and retrieval security review

**Scope:** historical branch `iskra-tenant-rag` at commit `49b449ed05a500e0c3557fa79ad7d09932100b95`. This is a static review of its document pilot, not a penetration test or production certification.

## Executive decision

**Do not bulk-merge the historical branch or enable customer uploads from it.** The branch contains useful, testable ideas for tenant-key authentication, SQLite FTS5, bounded upload size, text chunking, source excerpts, key rotation and tenant deletion. It is a monolithic prototype and needs a modular redesign before it can be used with confidential customer data.

The current modular core has server-derived Principals, tenant-bound storage factories and PostgreSQL RLS foundations. The document layer must use those existing contracts; it must not introduce a second tenant identity or trust a tenant ID from a request.

## Useful controls already present in the historical prototype

- Per-tenant API keys are random and only SHA-256 digests are stored.
- Tenant identity is derived from the validated key in WSGI middleware.
- Uploads have an 8 MiB request/file limit, allow-listed extensions and safe filename normalization.
- TXT, PDF and DOCX extraction is implemented; PDF page count is capped at 200.
- DOCX extraction reads only `word/document.xml` and caps its declared uncompressed size.
- Extracted text is capped at 1.5 million characters and split into overlapping chunks.
- Documents are deduplicated per tenant by content SHA-256.
- Document/chunk tables carry tenant IDs; list, search and delete queries include tenant filters.
- Search uses parameterized FTS5 MATCH input and returns source excerpts rather than fabricating a generated answer.
- Tenant keys can be rotated and tenant data can be deleted.
- Tests cover basic cross-tenant retrieval and deletion boundaries, malformed uploads, DOCX extraction and end-to-end tenant API behavior.

These controls are a starting point, not proof of safe ingestion.

## Blockers and risks to resolve before integration

### 1. Private database files and filesystem safety

The historical `knowledge.py` creates the document database without enforcing owner-only directory/file permissions and without rejecting symlink paths. That database contains customer text and must be treated as highly sensitive.

Required redesign:
- use a dedicated private data directory (0700) and database files (0600);
- reject symlinks and non-regular database files; avoid unsafe path races where supported;
- validate resolved paths against the configured storage root;
- keep secrets, raw tokens, extracted text and query contents out of logs;
- define encrypted backup, restore, retention and deletion behavior.

### 2. Parser resource exhaustion

The TXT limit is naturally bounded by upload bytes. DOCX bounds the selected XML part, but does not fully validate archive entry count, compression ratio or all container metadata. PDF limits page count, but extraction can expand compressed streams and create large intermediate strings before the final extracted-character cap is checked.

Required redesign:
- inspect archive metadata before reading; cap entry count, total uncompressed bytes, per-entry bytes and compression ratio;
- reject encrypted, malformed, duplicate-path and unsupported archive entries;
- use hardened XML parsing (e.g. `defusedxml`) and reject DTD/entity declarations;
- apply PDF byte, page, object, extracted-character, CPU and wall-clock limits;
- parse untrusted files in a resource-limited worker/process, not inside the web request process;
- cap per-page and aggregate extraction while streaming instead of building an unbounded intermediate string.

### 3. File type and content validation

The historical prototype relies mainly on filename extension. It does not establish that the file content matches the declared type, and there is no malware scanning or quarantine lifecycle.

Required redesign:
- validate extension and file signature/parser compatibility;
- reject polyglot, encrypted and unsupported files;
- quarantine uploads until extraction and scanning complete;
- record parser version and extraction status;
- never serve uploaded originals from a public path.

### 4. Tenant isolation and transactional integrity

The historical SQL generally filters by tenant ID, but the module is separate from the current Principal and storage interfaces. The FTS join matches chunk ID only; it should also assert tenant/document consistency. Initialization uses a process-local cache/lock and does not provide a cross-process migration/locking protocol.

Required redesign:
- derive tenant scope exclusively from `Principal` in a domain service;
- use composite keys and foreign keys including `tenant_id` for documents and chunks;
- join FTS rows to chunks/documents on both IDs and tenant scope;
- make document, chunk and FTS writes one transaction;
- make schema migrations idempotent and concurrency-safe;
- add negative tests for cross-tenant list, search, read, replace, delete and FTS corruption;
- use PostgreSQL RLS for multi-instance production, with a dedicated NOSUPERUSER/NOBYPASSRLS runtime role.

### 5. Retrieval quality and prompt-injection boundary

The historical prototype implements lexical FTS5 only. It does not implement semantic embeddings, reranking, generated answers or source citations. This is safer than claiming complete RAG, but it is not yet an assistant grounded in customer documents.

Before model generation:
- treat every retrieved chunk as untrusted data, never as system/developer instructions;
- preserve document ID, tenant ID, chunk ID and source metadata through retrieval;
- require citations for factual claims and return “not found” when evidence is insufficient;
- evaluate prompt injection in PDF/DOCX/TXT, data exfiltration attempts and cross-tenant retrieval;
- add deterministic retrieval fixtures and answer-grounding evaluations.

## Recommended modular target

```text
Flask route
  -> verified Principal
  -> DocumentService (authorization, quotas, idempotency)
  -> safe parser worker (type checks, limits, quarantine)
  -> TenantDocumentRepository (documents + chunks + FTS/vector)
  -> RetrievalService (tenant filter + ranking + source metadata)
  -> optional grounded LLM answer (untrusted context boundary + citations)
```

Storage interfaces must accept the trusted Principal or an already-verified tenant scope object, not a tenant ID copied from a request. Uploads remain disabled by default until the parser and storage gates pass.

## Required acceptance tests

- Oversized request, oversized extracted text, excessive PDF pages, compressed PDF expansion and parser timeout.
- DOCX ZIP bomb, excessive entries, malformed XML, DTD/entity payload and duplicate archive paths.
- Extension/content mismatch, encrypted/unsupported PDF, empty extraction and malformed file.
- Symlink database path, unsafe directory/file permissions, database replacement and corrupt database recovery.
- Tenant A cannot list, search, read, update or delete tenant B documents or chunks, including through FTS joins and malformed identifiers.
- Concurrent duplicate upload, concurrent first schema initialization, interrupted write and rollback.
- Token expiry/revocation, rate limiting, audit redaction and deletion/retention behavior.
- Retrieval prompt injection, source attribution, insufficient evidence and no-answer behavior.

## Status

Historical prototype: audited as a reference only. No document ingestion or customer RAG code has been enabled in the modular production path. The next implementation stage is a separately tested, feature-flagged document service with secure parsing and tenant-safe persistence.
