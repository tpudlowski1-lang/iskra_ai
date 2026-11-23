# External LLM provider allowlist

**Status:** implemented in the integrated draft candidate; not deployed.  
**Default:** deny outbound provider calls.

## Policy

The router accepts a provider only when its name is explicitly present in `LLM_ALLOWED_PROVIDERS`. The variable is a comma-separated list of provider names:

- `openai`
- `deepseek`
- `gemini`

If the variable is unset or empty, all external providers are disabled and `RouterProvider.generate()` returns `None` without invoking a provider. Unknown names are ignored; a misspelled value therefore does not enable a provider.

The primary provider (`LLM_PROVIDER`) and fallback order (`LLM_FALLBACK_PROVIDERS`) are preferences, not permissions. Every candidate is checked against the allowlist immediately before its provider function is called. A fallback not present in the allowlist never receives the prompt.

## Configuration examples

Disable all external providers (safe default):

```dotenv
# LLM_ALLOWED_PROVIDERS intentionally unset or empty
```

Approve DeepSeek only:

```dotenv
LLM_ALLOWED_PROVIDERS=deepseek
LLM_PROVIDER=deepseek
LLM_FALLBACK_PROVIDERS=
```

Approve OpenAI and DeepSeek, with DeepSeek primary:

```dotenv
LLM_ALLOWED_PROVIDERS=deepseek,openai
LLM_PROVIDER=deepseek
LLM_FALLBACK_PROVIDERS=openai
```

Do not enable a provider solely because its API key exists. The operator must first approve its data-handling terms, data classes, account/project settings, region, retention and contractual requirements. API keys remain in the host secret manager.

## Limitations

- This allowlist is a deployment-level gate, not a per-tenant policy.
- It does not redact sensitive prompt content or minimize context.
- It does not verify the provider account's Paid/Unpaid status, DPA, region or retention settings.
- It does not prevent other application code from making direct HTTP requests outside this router.
- It does not replace network egress restrictions or a separate local-only inference architecture.
- The autonomous worker now uses a fixed public taxonomy rather than serializing the mutable global graph; see `AUTONOMOUS_WORKER_DATA_MINIMIZATION.md`. Keep it disabled until singleton coordination, provider terms and operational gates are reviewed.

## Verification

The router unit tests cover:
- empty allowlist denies all provider calls;
- only allowlisted providers are called;
- unapproved fallback never receives the prompt;
- unknown allowlist entries do not enable a provider;
- JSON validation and fallback to an approved provider remain functional.

A successful test suite verifies this code path, not vendor contracts or legal compliance.
