# Provider data flow and privacy assessment

**Assessment date:** 2026-11-23  
**Scope:** source-code inspection of `refactor/modular-core`, specifically `iskra/llm/router.py`, `iskra/workers/autonomous.py`, `app.py`, `iskra/config.py`, `iskra/api/routes.py` and `wsgi.py`. This is an engineering inventory, not a legal opinion or a vendor privacy certification.

## Executive finding

Iskra's LLM router sends the supplied prompt to whichever external provider is enabled and succeeds first. The autonomous worker currently builds its prompt by serializing the complete in-memory knowledge graph and embedding that snapshot in the prompt. The router has no field-level redaction, tenant-aware prompt filtering, per-provider data policy, retention control, or user consent workflow.

The autonomous loop is opt-in: it starts only when `ENABLE_AUTONOMOUS_LOOP=true` (or an accepted truthy equivalent) **and** `ISKRA_PROCESS_ROLE=worker`. The web process does not start this loop. In the inspected application path, the autonomous worker is the visible caller of `RouterProvider.generate`; the current Flask API blueprint exposes graph/health routes, not a customer chat endpoint. This statement is limited to the inspected source files and does not rule out out-of-repository callers.

**Release consequence:** do not place confidential, personal, customer, or regulated information in the graph while an external provider is enabled unless the relevant provider, processing purpose, legal basis, contract, retention settings and customer disclosures have been reviewed and approved.

## Observed data flow

| Stage | Observed behavior | Privacy/security implication |
|---|---|---|
| Worker activation | Requires explicit worker role and opt-in environment flag | A dedicated worker is required; enabling the flag alone in a web process does not start the loop |
| Prompt construction | Serializes `self.siec.dane` with JSON and inserts the entire snapshot into the autonomous prompt | The whole graph may be disclosed to the selected model provider, not just the newly generated concepts |
| Provider selection | `LLM_PROVIDER` defaults to `deepseek`; `LLM_FALLBACK_PROVIDERS` defaults to `openai,gemini` | A prompt can be sent to more than one vendor during fallback |
| OpenAI | POST to configurable `OPENAI_BASE_URL`, default `https://api.openai.com/v1/chat/completions`; model defaults to `gpt-4o-mini` | Prompt and system instruction are included in JSON request body |
| DeepSeek | POST to configurable `DEEPSEEK_BASE_URL`, default `https://api.deepseek.com/v1/chat/completions`; model defaults to `deepseek-chat` | Prompt and system instruction are included in JSON request body |
| Gemini | POST to Google Generative Language `v1beta/models/{GEMINI_MODEL}:generateContent`; model must be configured | Prompt is sent in `contents.parts.text`; API key is sent in `x-goog-api-key` header |
| Retry behavior | Each provider request is attempted up to two times; timeout is 45 seconds, with a 2-second pause before a retry | A transient failure can cause repeated transmission to the same provider |
| Fallback behavior | Providers are tried sequentially until a valid JSON object is returned or the list is exhausted | One logical operation may result in requests to multiple providers |
| Logging | Router logs provider names, HTTP status codes and exception class names; it does not intentionally print prompt text or raw response bodies | This is not a complete audit trail; hosting/platform logs still need review |
| Persistence | This router module does not implement prompt retention/deletion controls or a provider-side data lifecycle | Retention, training-use, region and deletion behavior must be verified against each vendor's current contract/settings |

## Configuration inventory

| Variable | Purpose | Code default / behavior |
|---|---|---|
| `LLM_PROVIDER` | Primary provider | `deepseek` |
| `LLM_FALLBACK_PROVIDERS` | Ordered fallbacks | `openai,gemini` |
| `OPENAI_API_KEY` | OpenAI credential | Empty disables provider |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint | OpenAI chat completions URL |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o-mini` |
| `DEEPSEEK_API_KEY` | DeepSeek credential | Empty disables provider |
| `DEEPSEEK_BASE_URL` | DeepSeek-compatible endpoint | DeepSeek chat completions URL |
| `DEEPSEEK_MODEL` | DeepSeek model | `deepseek-chat` |
| `GEMINI_API_KEY` | Gemini credential | Empty disables provider |
| `GEMINI_MODEL` | Gemini model | Empty disables provider |
| `ENABLE_AUTONOMOUS_LOOP` | Enables autonomous work | Defaults to false |
| `ISKRA_PROCESS_ROLE` | Process role | Defaults to `web`; worker loop requires `worker` |

Credentials are read from environment variables. They must be injected through the hosting secret manager and must never be committed to the repository, included in prompts, or returned to clients.

## Confirmed gaps (not implemented by the inspected code)

- No per-tenant provider allowlist or provider selection policy in the router.
- No prompt-level PII/secret detection, redaction, minimization or size-based data classification.
- No consent, customer disclosure or purpose-selection workflow before sending graph data to a third party.
- No provider-specific retention, region, training-use, deletion or DPA state represented in application configuration.
- No per-tenant spend/usage quota or provider request budget in this router.
- No structured request audit event with a safe prompt hash, tenant/purpose identifiers and provider outcome.
- No automatic suppression of fallback to a vendor that has not been approved for the data classification.
- No customer-facing chat route was found in the inspected Flask API blueprint; the visible application API exposes graph endpoints. Reassess this boundary whenever new routes or integrations are added.

## Required actions before commercial customer data is enabled

1. **Define data classes:** public, internal, confidential, personal and special-category/regulated data. Set explicit prohibited classes for external LLM calls until legal/security review.
2. **Minimize prompts:** send only the specific graph subset needed for the operation; do not serialize the full tenant graph by default.
3. **Enforce tenant boundaries:** derive tenant identity from the verified server-side principal and select only that tenant's data. Never trust a tenant identifier supplied in a prompt or request body.
4. **Provider allowlist:** make approved providers explicit per deployment and data class. Disable unapproved fallbacks rather than silently routing to them.
5. **Retention and disclosure:** document purpose, categories of data, destinations, region, retention, training-use settings, deletion route and subprocessors. Obtain and review current DPA/terms and customer-facing disclosures before processing personal/customer data.
6. **Secrets and logs:** keep credentials in a secret manager; redact tokens and personal data from application, proxy and platform logs; define log retention and access controls.
7. **Budgets and resilience:** add per-tenant request/token/cost limits, bounded retries, circuit breakers and an operator kill switch.
8. **Verification:** add tests proving that sensitive fields are not sent, unapproved providers are never called, fallback obeys the allowlist, tenant A data cannot enter tenant B prompts, and opt-out prevents outbound calls.
9. **Operational review:** complete a vendor/subprocessor register, data-flow diagram, retention schedule, incident process and legal review before paid launch.

## Evidence and limitations

- `iskra/llm/router.py`: provider endpoints, request payloads, key headers, retry count, timeout, fallback order and log statements.
- `iskra/workers/autonomous.py`: worker opt-in conditions and full graph serialization into the prompt.
- `iskra/api/routes.py`: current blueprint routes are graph and health endpoints; no chat endpoint is defined there.
- `app.py`: constructs the graph and autonomous worker and registers the blueprint.
- `iskra/config.py`: storage settings; no LLM privacy/retention configuration is present there.
- `wsgi.py`: production API-token middleware wrapper.

This assessment does **not** determine the providers' current contractual or technical data handling. It does not establish GDPR compliance, a lawful basis, adequacy of international transfers, or a completed DPIA. Those require current vendor documentation, deployment-specific settings, processing context and qualified legal review.
