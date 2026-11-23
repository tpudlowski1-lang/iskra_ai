# External LLM processing policy

## Default-deny behavior

The router blocks every external provider call unless the server operator explicitly sets:

- `LLM_ALLOW_EXTERNAL_PROCESSING=true`
- `LLM_ALLOWED_EXTERNAL_PROVIDERS` to a comma-separated allowlist containing only `openai`, `deepseek`, and/or `gemini`.

An empty or missing allowlist denies all providers. Unknown names are ignored. The policy is checked before invoking a provider; primary and fallback providers use the same check. The settings are server-side environment variables and are not read from request bodies or prompts.

Example for an operator-approved DeepSeek-only environment:

```dotenv
LLM_ALLOW_EXTERNAL_PROCESSING=true
LLM_ALLOWED_EXTERNAL_PROVIDERS=deepseek
LLM_PROVIDER=deepseek
LLM_FALLBACK_PROVIDERS=
```

Privacy hold:

```dotenv
LLM_ALLOW_EXTERNAL_PROCESSING=false
LLM_ALLOWED_EXTERNAL_PROVIDERS=
```

## Limitations and release gates

- This is an application-level gate for providers registered in `iskra/llm/router.py`, not a network egress firewall. Other code paths and dependencies require separate audit.
- Enabling a provider is not proof of user notice/consent, a data-processing agreement, transfer mechanism, or GDPR compliance.
- Review custom endpoint settings such as `OPENAI_BASE_URL`; provider identifiers alone do not verify the endpoint owner.
- No automatic PII/secret redaction is claimed. Do not send credentials, personal/special-category data, confidential customer data, or tenant data until classification, tenant-scoped context, provider terms, retention, region, training-use and deletion are reviewed.
- The autonomous worker remains disabled by default. Its current global-graph context must be replaced with bounded, tenant-scoped and classified context before customer-data use.
- A blocked request returns `None`; callers must handle unavailable inference and must not silently switch to an ungoverned external API.

This is a technical control and release gate, not legal advice or a compliance certification.
