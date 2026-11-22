# Iskra AI Modular Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Incrementally modularize Iskra AI while preserving its existing API, graph data, and reliability guarantees.

**Architecture:** A modular Flask monolith with `app.py` retained as a compatibility entry point. Extract bounded modules behind stable interfaces; keep persistence migration and tenant isolation as later independently testable projects.

**Tech Stack:** Python 3.11, Flask 3, requests, Gunicorn, unittest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-23-modular-core-design.md`

## Global Constraints
- Preserve `/`, `/api/network`, and `/health`.
- Preserve the twelve foundational knowledge pillars and JSON compatibility.
- Keep `ENABLE_AUTONOMOUS_LOOP=false` by default.
- Never commit API keys or customer data.
- Do not merge into `main` automatically.
- Do not claim a test passes without a fresh CI result.

## Review Focus
- Malformed or hostile graph labels must display as plain text, not executable HTML.
- Missing provider credentials must skip that provider without leaking secrets.
- Parallel requests and writes must not lose graph updates.
- Corrupt legacy JSON must be preserved for diagnosis and recover safely.
- Autonomous jobs must not start implicitly in multi-worker deployments.

---

### Task 1: Security baseline and CI trigger

**Status: complete on this branch.**

**Files:**
- Modify: `app.py`
- Modify: `.github/workflows/iskra-quality-gates.yml`
- Create: `tests/test_security_baseline.py`

- [x] Replace dashboard `innerHTML` rendering with DOM nodes and `textContent`.
- [x] Add baseline response security headers.
- [x] Add tests for safe dashboard rendering and headers.
- [x] Run the complete existing test suite and security tests.
- [x] Trigger GitHub Actions on this branch and inspect the actual run.

### Task 2: Package boundaries and compatibility façade

**Status: complete for configuration, package boundaries, and worker opt-in; deeper module extraction continues incrementally.**

**Files:**
- Create: `iskra/__init__.py`, `iskra/config.py`
- Create: `iskra/knowledge/__init__.py`, `iskra/llm/__init__.py`, `iskra/api/__init__.py`, `iskra/security/__init__.py`, `iskra/workers/__init__.py`
- Modify: `app.py`
- Create: focused import and compatibility tests.

- [x] Introduce immutable environment configuration with validated numeric bounds.
- [x] Keep `app.py` import compatibility and existing global names during extraction.
- [x] Ensure importing the application has no unexpected background side effects.
- [x] Run all tests.

### Task 3: Extract knowledge graph and provider router

**Status: complete; latest upstream graph hardening retained.**

**Files:**
- Create: `iskra/knowledge/graph.py`
- Create: `iskra/llm/router.py`
- Modify: `app.py`
- Modify: tests to import both new modules and legacy façade.

- [x] Move graph and provider implementations without changing public behavior.
- [x] Keep compatibility aliases in `app.py`.
- [x] Add direct module-level tests.
- [x] Run all deterministic, thread, and process tests.

### Task 4: Storage boundary and migration design

**Status: protocol and migration policy added; database adapter and transactional migration remain deferred.**

**Files:**
- Create: `iskra/storage/__init__.py`, `iskra/storage/protocols.py`, `docs/DATA_MIGRATION.md`
- Add interface contract tests.

- [ ] Define a repository protocol without silently switching the production store.
- [ ] Document JSON backup, validation, rollback, and future SQLite/PostgreSQL migration.
- [ ] Do not change the persisted format until migration tests exist.

### Task 5: Production readiness gates

**Status: partial; readiness blockers documented.**

**Files:**
- Update: `.github/workflows/iskra-quality-gates.yml`
- Create: security and architecture documentation.

- [ ] Add dependency/security checks that do not require secrets.
- [ ] Add explicit deployment-readiness checklist.
- [x] Document unresolved tenant, auth, RAG, durable-storage, and observability blockers.
- [ ] Request review before any merge.

