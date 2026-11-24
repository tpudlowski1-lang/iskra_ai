# Iskra AI — staging verification plan

Status: test plan only. No live Render deployment, customer data, provider calls, or production database was used to create this document.

## 1. Current verified architecture facts

- WSGI selects the registry with `ISKRA_CREDENTIAL_STORE_BACKEND`. PostgreSQL uses the runtime login from `ISKRA_CREDENTIAL_POSTGRES_DSN` and the server-side `ISKRA_CSRF_HMAC_SECRET`. Local single-instance SQLite uses `ISKRA_CREDENTIAL_DB_PATH`.
- Browser sessions depend on the persistent credential registry. A static legacy `API_TOKEN` is not sufficient to exchange into a browser session.
- The browser session contract uses an opaque `__Host-iskra_session` cookie with Secure, HttpOnly, SameSite=Strict and Path=/, an eight-hour maximum lifetime, and session-bound CSRF checks for cookie-authenticated mutations.
- Revoking or rotating the underlying API credential invalidates the browser session.
- Provider inference is deny-by-default unless both deployment-level and tenant-level provider allowlists approve a provider.
- Document ingestion and the autonomous worker must remain disabled during initial staging.

## 2. Prepare the staging database and web process

Use the staging blueprint on the reviewed commit. Keep one Gunicorn worker and a private persistent disk for the global JSON graph. The tenant graph, documents and credential registry use PostgreSQL. Follow [the pilot guide](INSTALL_PILOT.md) to provision distinct roles. The WWW process receives the credential runtime and tenant-data logins. The credential operator runs separately.

Record the commit, deployment ID, region and database version. Exercise the public HTTPS URL before and after a restart and a redeploy. Keep status codes and fixture identifiers. Redact cookies, credentials, signing keys and connection strings from evidence.

## 3. Safe staging configuration

- `ENABLE_AUTONOMOUS_LOOP=false`
- Do not set `ISKRA_PROCESS_ROLE=worker`
- `ISKRA_ENABLE_DOCUMENT_INGESTION=false`
- `LLM_ALLOWED_PROVIDERS=` (empty)
- `ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON={}`
- Keep provider API keys unset until provider/data-processing review is complete.
- Set `DATA_DIR` on the private disk. Select PostgreSQL for all three backends and configure both runtime DSNs.
- One instance; no customer or regulated data; use synthetic test tenants only.
- `API_TOKEN` and issued credentials must be generated and stored in the hosting secret manager; never place them in Git, tickets, logs, or chat.

## 4. Staging test matrix

| ID | Test | Expected result | Evidence required |
|---|---|---|---|
| ST-01 | GET /health | HTTP 200, no secret leakage | HTTP response |
| ST-02 | Protected endpoint without credential | 401 or documented fail-closed 503 | HTTP response |
| ST-03 | Invalid/revoked/expired credential | Rejected | HTTP response and safe audit event |
| ST-04 | Persistent credential issuance | Token shown once; only digest persisted | DB inspection without exposing token |
| ST-05 | Browser login with persistent tenant credential | 201 and secure host cookie | Cookie name and attributes, value redacted |
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
