# Iskra AI — staging verification plan

Status: test plan only. No live Render deployment, customer data, provider calls, or production database was used to create this document.

## 1. Current verified architecture facts

- WSGI configures the persistent credential/session registry only when `ISKRA_CREDENTIAL_DB_PATH` is set.
- The current registry implementation is SQLite and explicitly documents that it is single-instance; multiple application instances require a PostgreSQL-backed credential/session store.
- Browser sessions depend on the persistent credential registry. A static legacy `API_TOKEN` is not sufficient to exchange into a browser session.
- The browser session contract uses an opaque `__Host-iskra_session` cookie with Secure, HttpOnly, SameSite=Strict and Path=/, an eight-hour maximum lifetime, and session-bound CSRF checks for cookie-authenticated mutations.
- Revoking or rotating the underlying API credential invalidates the browser session.
- Provider inference is deny-by-default unless both deployment-level and tenant-level provider allowlists approve a provider.
- Document ingestion and the autonomous worker must remain disabled during initial staging.

## 2. Deployment blocker to resolve before browser UI testing

The inspected `render.yaml` does not set `ISKRA_CREDENTIAL_DB_PATH` and does not declare a persistent disk. WSGI therefore has no configured persistent credential store from this manifest alone. The browser login/session flow cannot be considered ready from this manifest.

For a temporary single-instance staging deployment, configure a private persistent disk and point `ISKRA_CREDENTIAL_DB_PATH` to a database file inside that disk, using a private parent directory. Do not use an ephemeral filesystem path for credentials or sessions. Keep one web instance only.

Before any multi-instance or commercial deployment, replace the SQLite credential/session backend with a reviewed PostgreSQL-backed implementation and test its migrations, locking, revocation, expiry and fail-closed behavior. Do not simply point SQLite at a shared network filesystem.

## 3. Safe staging configuration

- `ENABLE_AUTONOMOUS_LOOP=false`
- Do not set `ISKRA_PROCESS_ROLE=worker`
- `ISKRA_ENABLE_DOCUMENT_INGESTION=false`
- `LLM_ALLOWED_PROVIDERS=` (empty)
- `ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON={}`
- Keep provider API keys unset until provider/data-processing review is complete.
- `ISKRA_CREDENTIAL_DB_PATH` must point to the private persistent disk only after it is provisioned.
- One instance; no customer or regulated data; use synthetic test tenants only.
- `API_TOKEN` and issued credentials must be generated and stored in the hosting secret manager; never place them in Git, tickets, logs, or chat.

## 4. Staging test matrix

| ID | Test | Expected result | Evidence required |
|---|---|---|---|
| ST-01 | GET /health | HTTP 200, no secret leakage | HTTP response |
| ST-02 | Protected endpoint without credential | 401 or documented fail-closed 503 | HTTP response |
| ST-03 | Invalid/revoked/expired credential | Rejected | HTTP response and safe audit event |
| ST-04 | Persistent credential issuance | Token shown once; only digest persisted | DB inspection without exposing token |
| ST-05 | Browser login with persistent tenant credential | 201 and secure host cookie | Set-Cookie headers |
| ST-06 | Browser login with static legacy API_TOKEN | 403 persistent_credential_required | HTTP response |
| ST-07 | Browser mutation without CSRF | 403 | HTTP response |
| ST-08 | Cross-origin or cross-site mutation | 403 | HTTP response |
| ST-09 | Same-origin mutation with valid CSRF | Expected success for authorized role | HTTP response |
| ST-10 | Logout | Session invalidated and cookie cleared | HTTP response |
| ST-11 | Revoke/rotate credential after login | Existing browser session rejected | HTTP response |
| ST-12 | Restart one instance with persistent disk | Credentials remain valid; session behavior matches documented expiry | Before/after restart |
| ST-13 | Restart with ephemeral storage (negative control only) | Data loss detected; proves why ephemeral storage is prohibited | Before/after comparison |
| ST-14 | Two synthetic tenants query each other's identifiers | No cross-tenant records or citations | Automated integration test |
| ST-15 | Tenant provider allowlist missing/empty | No external model call; inference unavailable | Mocked provider transport |
| ST-16 | Fallback provider not in both allowlists | Fallback blocked; no silent data transfer | Mocked provider transport |
| ST-17 | Database unavailable | Fail closed; no static-token fallback bypass | HTTP response |
| ST-18 | Document ingestion endpoint while disabled | Rejected/not available | HTTP response |
| ST-19 | Autonomous worker while disabled | No worker starts in web process | Process/log inspection |
| ST-20 | Backup and restore | Restored credential store passes integrity and auth checks | Restore log and tests |

## 5. Required adversarial tests

Use synthetic strings only:
- Prompt injection inside retrieved text: the model must treat it as untrusted content.
- Cross-tenant citation ID: reject it; do not return another tenant's source.
- Secret-shaped values in prompt/excerpts: verify the documented minimizer redacts supported patterns; also test unsupported formats to document misses.
- Provider failure: verify fallback is constrained by the exact same allowlists.
- Malformed/oversized credentials and malformed JSON: reject safely without traceback or secret logging.
- CSRF token mismatch, missing token, cross-origin Origin, cross-site Fetch Metadata and HTTPS downgrade: reject mutations.

## 6. Release gates

Do not approve production until all of the following are evidenced:
1. The credential/session store is durable and appropriate for the deployment topology.
2. Tenant isolation and citation scoping pass on the actual database backend.
3. Backup and restore are tested.
4. Provider terms, data location, retention, DPA and customer notice/consent are reviewed; no customer data is sent before approval.
5. Logs and error responses are checked for credentials, prompts, personal data and tokens.
6. Deployment rollback and incident-response procedures are tested.
7. An independent security review has no unresolved critical/high findings.

A green GitHub Actions run is necessary but does not replace these staging and operational gates.
