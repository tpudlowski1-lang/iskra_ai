# LLM provider data flow and privacy controls

## Verified code path

The provider router supports OpenAI-compatible, DeepSeek and Gemini endpoints. When a provider succeeds, the application sends the supplied prompt to that external provider over HTTPS. Provider selection and credentials are controlled by server environment settings; no customer-facing provider consent or per-tenant provider selection UI is implemented.

The autonomous knowledge worker is disabled by default. It only starts when both `ENABLE_AUTONOMOUS_LOOP=true` and `ISKRA_PROCESS_ROLE=worker` are configured. In each cycle it serializes the entire legacy global knowledge graph (`siec.dane`) into a prompt and passes that prompt to the configured LLM router. This means the complete current global graph may be transmitted to whichever external provider is selected as primary or fallback. The graph is not automatically redacted or filtered by tenant.

The current worker reads and updates the legacy global graph, not tenant-specific graph records. Do not place customer records, credentials, personal data, confidential business data, secrets, access tokens or regulated information in that global graph. Keep the autonomous worker disabled until the operator has reviewed the content and provider terms for the chosen environment.

## What the code does and does not do

Implemented:
- Provider API keys are read from environment variables and are not included in the prompt payload.
- HTTP calls use a 45-second timeout and two attempts per provider.
- The router logs provider names, HTTP status codes and exception types; it does not intentionally log the prompt body or API key.
- The autonomous worker is opt-in and is not started inside ordinary WSGI web workers.
- The worker's prompt currently includes the entire serialized global graph.

Not implemented:
- Per-tenant provider routing or provider allowlists.
- User-facing notice/consent and controls for external processing.
- Prompt-level PII/secret detection, redaction or data minimization.
- Provider-specific retention, region, training-use or deletion configuration.
- A central record of which provider received which prompt, with safe data classification metadata.
- A local-only inference mode enforced by policy.
- A guarantee that provider-side retention/deletion behavior matches Iskra's intended retention policy.

## Release requirements before customer data can be sent to an external model

1. Define data classes (public, internal, confidential, personal/special-category) and prohibit secrets/credentials in prompts.
2. Decide which data classes may be sent to each provider; default-deny confidential and personal data until contract, region, retention and transfer reviews are complete.
3. Add server-side provider allowlists and explicit opt-in for external processing. Do not rely on user-supplied prompt text to choose a provider.
4. Add tenant-scoped context construction and strict data minimization; never serialize the global graph into a tenant request.
5. Add deterministic redaction for credentials and high-confidence sensitive identifiers before any network call; treat this as defense in depth, not a guarantee.
6. Provide a local-only mode whose policy rejects all external network providers, not merely a UI preference.
7. Document provider/subprocessor roles, data location, retention, training use, deletion, incident terms and transfer mechanism in customer-facing privacy information and agreements.
8. Test that provider fallbacks obey the same allowlist and data-classification policy; fallback must not silently send a prompt to a less-approved provider.
9. Add audit events with request ID, tenant ID, data classification and provider name, while excluding prompt bodies, secrets and personal content.
10. Validate retention/deletion behavior and incident handling with each provider before launch.

## Operational safe defaults

- Keep `ENABLE_AUTONOMOUS_LOOP=false` in all web services.
- Do not set `ISKRA_PROCESS_ROLE=worker` on a customer-facing environment until provider/data-flow review is complete.
- Keep provider API keys in the host secret manager.
- Do not enable customer document uploads or RAG merely because document storage exists; document parsing and external LLM transmission need separate approval and controls.
- Treat all provider calls as external data transfers. HTTPS protects transport, not provider-side use or retention.

## Current commercial gate

This document describes current code behavior and missing controls; it is not a legal opinion or evidence of GDPR compliance. Customer-data processing through external LLMs is **not approved for production** until the above controls, contractual review and customer-facing disclosures are complete. A successful CI run does not satisfy this gate.


## Exact provider request behavior (source audit, 2026-11-23)

The following details are read from `iskra/llm/router.py`; they describe code defaults, not a recommendation to enable every provider.

| Provider | Endpoint default | Model default | Request body / authentication |
|---|---|---|---|
| OpenAI-compatible | `https://api.openai.com/v1/chat/completions` (overridable with `OPENAI_BASE_URL`) | `gpt-4o-mini` | JSON `messages` includes a system instruction and the supplied prompt; bearer API key; requests JSON-object output |
| DeepSeek | `https://api.deepseek.com/v1/chat/completions` (overridable with `DEEPSEEK_BASE_URL`) | `deepseek-chat` | Same OpenAI-compatible chat-completions shape; bearer API key; requests JSON-object output |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent` | No default; `GEMINI_MODEL` is required | Prompt is sent as `contents[0].parts[0].text`; API key is supplied in `x-goog-api-key`; requests `application/json` output |

Configuration variables observed in code:

- `LLM_PROVIDER`: primary provider; defaults to `deepseek`.
- `LLM_FALLBACK_PROVIDERS`: comma-separated fallback list; defaults to `openai,gemini`.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`.
- `GEMINI_API_KEY`, `GEMINI_MODEL`.
- `ENABLE_AUTONOMOUS_LOOP`: defaults to false.
- `ISKRA_PROCESS_ROLE`: defaults to `web`; worker role is required to start the autonomous loop.

The router uses a 45-second request timeout and up to two attempts per provider, with a two-second pause before the second attempt. The primary provider plus configured fallbacks are attempted sequentially until a valid JSON object is returned. With three enabled providers, a single logical generation can therefore result in up to six HTTP attempts in the worst case. Missing credentials/model configuration cause that provider to be skipped.

The router prints provider names, HTTP status codes, exception class names and success/failure messages. It does not intentionally print the prompt body, raw model response or API key. This does not establish that reverse proxies, hosting logs, crash reports or provider-side systems never record request metadata or content; those systems require separate review.

## Configuration and deployment decision

For an environment that has not passed provider/privacy review:

- Leave the autonomous loop disabled (`ENABLE_AUTONOMOUS_LOOP=false`).
- Do not run a process with `ISKRA_PROCESS_ROLE=worker`.
- Do not configure provider credentials unless a tested feature requires them and the data-flow has been approved.
- If external inference is not approved, do not rely on an empty fallback list as the only control. The current router has no enforced local-only policy; a local-only guarantee requires a code-level deny-external policy and negative network-call tests.
