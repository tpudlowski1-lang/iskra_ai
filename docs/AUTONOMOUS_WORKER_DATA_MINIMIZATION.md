# Autonomous worker: bounded public context

## Change

The autonomous research worker must not serialize `siec.dane` into an external LLM prompt. The mutable legacy graph can contain user-supplied or customer material and has no tenant-level classification. Instead, the worker builds its prompt from a fixed, code-defined public taxonomy of 12 foundational knowledge areas and 10 static relationships.

The context is bounded and independent of the contents of the live graph. The worker can propose new concepts and link them to the known public foundational identifiers. It does not receive arbitrary existing graph identifiers or labels.

## Safety properties tested

- A private marker stored in the mutable graph does not appear in the worker prompt.
- The prompt contains the fixed foundational identifiers only and is bounded in size.
- The worker remains opt-in and is not started in web-role processes.

## Limitations

- This reduces the worker's outbound context; it does not add PII detection/redaction to ordinary user prompts or other LLM call sites.
- The worker no longer sees custom graph nodes when planning new concepts. This is an intentional privacy/utility trade-off; expanding context requires a future data-classification and tenant-scoped design.
- Static taxonomy labels are sent to the configured provider only if the router's external-processing policy permits it. The router allowlist/default-deny control is tracked separately.
- This does not prove user consent, provider contractual suitability, retention/deletion behavior, or GDPR compliance.

Keep the autonomous worker disabled for customer-facing deployments until the full external-data-flow review and contractual gates are complete.
