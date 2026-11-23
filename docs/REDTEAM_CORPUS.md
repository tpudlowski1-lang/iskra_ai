# Iskra adversarial regression corpus v1

Status: draft test data; not wired to production and not a semantic pass result.

## Purpose
Provide a versioned, reviewable set of adversarial inputs covering direct and indirect prompt injection, privilege claims, tenant boundaries, secret disclosure, excessive agency, retrieval leakage, malformed inputs, and provider failure.

## Files
- `quality/redteam_scenarios.json`: scenario inputs and expected control objectives.
- `tests/test_redteam_corpus.py`: offline structural validation of the corpus.

## Run
```bash
python -m unittest tests.test_redteam_corpus -v
```

## Important limits
The tests validate only that the scenario dataset is complete and well-formed. They do not call an LLM, execute Iskra requests, evaluate semantic correctness, or prove prompt-injection resistance. A later integration stage should run these cases against a staging deployment with synthetic tenant data, record model/provider/version, and require human review of failures. Never use production secrets or real customer data in red-team fixtures.

## Recommended next integration
Use Promptfoo for repeatable local/CI adversarial execution once a stable, authenticated staging API target exists. Keep model-graded results separate from deterministic unit tests and do not make network/API-key tests mandatory for the offline baseline.
