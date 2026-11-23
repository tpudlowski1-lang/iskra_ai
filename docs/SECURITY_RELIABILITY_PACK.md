# Security & Reliability Regression Pack v1

This pack verifies authorization boundaries and provider failover behavior.

## Coverage
- Missing trusted principal returns 401.
- Wrong role returns 403.
- Correct role passes.
- System-wide admin endpoints require admin role AND system tenant.
- Unexpected provider exceptions do not interrupt fallback.
- If all providers raise, router returns None.

## Change
The LLM router catches provider exceptions at the provider boundary and continues to configured fallback providers. It logs exception class only, not provider exception message.

## Limits
Tests use Flask test clients and mocked provider functions. They do not verify live credentials, external API availability, production tenant deployment, or semantic prompt-injection behavior.
