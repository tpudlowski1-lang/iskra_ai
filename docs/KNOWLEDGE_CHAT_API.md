# Tenant knowledge chat API

## Endpoints

All endpoints require a trusted API-token Principal. Tenant ID is derived from the Principal installed by the WSGI authentication middleware; request JSON, query strings and model output cannot choose the tenant.

- POST /api/tenant/chat — member/admin. Accepts JSON with question (1–1000 chars). Searches only the Principal's tenant documents, passes at most five bounded excerpts to the LLM, and returns a source-grounded answer with server-resolved citations.
- GET /api/tenant/documents — member/admin. Lists only the current tenant's documents.
- GET /api/tenant/documents/search?q=... — member/admin. Searches only the current tenant's documents.
- POST /api/tenant/documents — admin only. Multipart file upload; disabled unless ISKRA_ENABLE_DOCUMENT_INGESTION=true.
- DELETE /api/tenant/documents/{document_id} — admin only. Deletion is tenant-scoped.

## Grounding contract

- If no sources are found, the service returns a no_sources response without calling an LLM.
- The model receives at most five excerpts, each truncated to 1,200 characters. It receives no tenant identifier or conversation history. Retrieval currently uses tenant-filtered SQLite FTS5 lexical search, not semantic/vector embeddings.
- The system prompt tells the model to treat excerpts as untrusted data and ignore embedded instructions.
- An answer must cite at least one exact document ID returned by tenant-scoped search. Unknown or cross-tenant citation IDs are rejected.
- If the model cannot support an answer, it must return an empty answer and empty citation list; the service returns no_answer.
- If no provider is explicitly allowlisted, inference is unavailable and the API returns 503.

## Safety and release gates

- The deployment-level LLM_ALLOWED_PROVIDERS allowlist is default-deny and applies to primary and fallback providers. It is not a per-tenant provider policy.
- Upload is disabled by default in code and in Render. Do not enable it for customer data until parser sandboxing, malware scanning, retention, audit, backup and incident-response controls are completed.
- The parser worker has resource/environment hardening but is not a full OS/container sandbox.
- Prompt-injection instructions in retrieved excerpts are mitigated by a separate system prompt and untrusted-data framing, but no deterministic test can prove universal resistance to model-based prompt injection.
- The /assistant browser UI is a minimal controlled-pilot interface only; there is no signup, account recovery, HTTP-only browser session, server-side conversation history, semantic/vector retrieval, per-tenant model policy, consent UI or ordinary-prompt PII/secret redaction yet.
- No live provider calls, customer documents or production deployment were used in CI.

This API is a technical foundation for an MVP, not evidence of production or commercial readiness.


## Minimal browser interface

A minimal responsive UI is served at /assistant. The user pastes an API token into a password field; JavaScript holds it in memory only and does not use localStorage or sessionStorage. The token is cleared on disconnect or page reload. The UI uses textContent for model output and citation labels. There is no public signup, account recovery, HTTP-only browser session, or chat history; token-based access is intended for a controlled pilot, not public SaaS.
