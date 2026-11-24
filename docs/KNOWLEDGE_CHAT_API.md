# Tenant knowledge chat API

## Endpoints

All tenant endpoints require a trusted server-side Principal. Tenant ID is derived from the Principal installed by WSGI authentication middleware; request JSON, query strings and model output cannot choose the tenant.

- POST /api/tenant/chat — member/admin. Accepts JSON with question (1–1000 chars). Searches only the Principal's tenant documents, passes at most five bounded excerpts to the LLM, and returns a source-grounded answer with server-resolved citations.
- GET /api/tenant/documents — member/admin. Lists only the current tenant's documents.
- GET /api/tenant/documents/search?q=... — member/admin. Searches only the current tenant's documents.
- POST /api/tenant/documents — admin only. Multipart file upload; disabled unless ISKRA_ENABLE_DOCUMENT_INGESTION=true.
- DELETE /api/tenant/documents/{document_id} — admin only. Deletion is tenant-scoped.
- GET /assistant — public static application shell; it contains no tenant data.
- POST /api/browser/session — exchanges a persistent tenant credential for a short-lived browser session.
- GET /api/browser/session and GET /api/tenant/session — inspect the current browser session and tenant context.
- POST /api/browser/session/logout — revokes the current browser session.

## Grounding contract

- If no sources are found, the service returns a no_sources response without calling an LLM.
- The model receives at most five excerpts, each truncated to 1,200 characters. It receives no tenant identifier or conversation history. Retrieval currently uses tenant-filtered SQLite FTS5 lexical search, not semantic/vector embeddings.
- The system prompt tells the model to treat excerpts as untrusted data and ignore embedded instructions.
- Best-effort outbound minimization redacts several common secret/token patterns, PEM private keys, email addresses and IBANs from questions and excerpts; document filenames are excluded from the model prompt. This is not complete DLP or anonymization.
- An answer must cite at least one exact document ID returned by tenant-scoped search. Unknown or cross-tenant citation IDs are rejected.
- If the model cannot support an answer, it must return an empty answer and empty citation list; the service returns no_answer.
- If no provider is explicitly allowlisted by both deployment-level and tenant-level policy, inference is unavailable and the API returns 503.

## Safety and release gates

- Both deployment-level `LLM_ALLOWED_PROVIDERS` and tenant-level `ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON` are default-deny. The tenant map is configured by the operator as JSON keyed by exact tenant ID, e.g. `{"tenant-acme":["deepseek"]}`. A provider is eligible only when approved by both lists; all primary/fallback providers are constrained by the intersection. Missing/invalid tenant policy denies chat inference. This is a technical allowlist, not a consent UI or legal approval.
- Upload is disabled by default in code and in Render. Do not enable it for customer data until parser sandboxing, malware scanning, retention, audit, backup and incident-response controls are completed.
- The parser worker has resource/environment hardening but is not a full OS/container sandbox.
- Prompt-injection instructions in retrieved excerpts are mitigated by a separate system prompt and untrusted-data framing, but no deterministic test can prove universal resistance to model-based prompt injection.
- The browser UI uses a server-side session cookie named `__Host-iskra_session` with Secure, HttpOnly, SameSite=Strict and Path=/ attributes. The raw persistent API credential is exchanged once and is not retained in JavaScript or browser storage. Browser sessions expire after at most eight hours and are invalidated when the underlying credential is revoked or rotated.
- Cookie-authenticated mutations require a session-bound `X-CSRF-Token` and same-origin/Fetch Metadata checks. Direct bearer-token API clients remain supported.
- This is not a complete identity product: public signup, password login, MFA, email verification, recovery, invitations, billing and server-side conversation history are not included.
- No live provider calls, customer documents or production deployment were used in CI.

This API is a technical foundation for a controlled MVP pilot, not evidence of production or commercial readiness.

## Minimal browser interface

A minimal responsive UI is served at `/assistant`. The user enters a persistent tenant credential into the password field. The browser sends it once to `/api/browser/session`; the server validates it and issues the HttpOnly session cookie. The raw credential is not retained in JavaScript state, localStorage or sessionStorage. The browser uses the session cookie for subsequent requests and obtains the session-bound CSRF token from the server. Model output and citation labels are rendered with DOM `textContent`.

Serve the interface over HTTPS. Browser sessions require the persistent credential registry and durable private storage configured through `ISKRA_CREDENTIAL_DB_PATH`; static legacy `API_TOKEN` credentials cannot be exchanged for browser sessions. SQLite credential/session storage is single-instance and is not a multi-instance production session backend.
