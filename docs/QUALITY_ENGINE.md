# Iskra Quality Engine v1

Status: isolated draft; no production runtime wiring.

## Purpose

Provide fast deterministic checks for response format and explicit regression markers. It uses only Python standard library and makes no network/model calls.

## Checks

- case-insensitive required phrase and prohibited phrase checks
- minimum character count
- maximum word count
- JSON parseability

## Running

```bash
python -m unittest tests.test_quality_engine -v
```

## Limits

These checks cannot reliably judge factuality, reasoning quality, harmfulness, or semantic prompt-injection resistance. They are a lightweight regression gate. Semantic model evaluation, retrieval metrics, and red-team coverage require a separate layer and must not be represented as passed by this engine.

## Integration policy

Do not wire into production requests. Add to CI after the project test discovery convention is confirmed. Scenario file is an initial contract, not a live benchmark. Keep tests deterministic and offline.
