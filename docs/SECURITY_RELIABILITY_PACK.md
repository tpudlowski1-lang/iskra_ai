# Security & Reliability Regression Pack v1

This pack verifies authorization boundaries and provider failover behavior.

## Coverage
- Missing trusted principal returns 401.
- Wrong role returns 403.
- Correct role passes.
- System-wide admin endpoints require admin role AND system tenant.
- Unexpected provider exceptions do not interrupt fallback.
- If all providers raise, router returns None.
- One shared, context-local 100-second generation deadline is propagated across the primary and fallback chain without changing the provider(prompt) extension API.
- Each HTTP attempt uses bounded connect/read timeouts derived from the remaining deadline; retry backoff is capped at one second, leaving headroom under Render/Gunicorn's 120-second worker timeout.
- Deadline state is isolated per concurrent execution context and reset in a finally block.

## Change
The LLM router catches provider exceptions at the provider boundary and continues to configured fallback providers. It logs exception class only, not provider exception message. The total chain now shares a 100-second deadline; the provider callback contract remains `provider(prompt)`.

## Limits
Tests use Flask test clients and mocked provider functions. The CI regression suite now includes shared-deadline propagation, deadline expiry and timeout-budget checks. It does not verify live credentials, external API availability, production tenant deployment, or semantic prompt-injection behavior.
