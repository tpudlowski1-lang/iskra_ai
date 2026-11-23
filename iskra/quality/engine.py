"""Deterministic, dependency-free response quality checks for Iskra AI."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def evaluate_response(response: str, checks: dict[str, Any]) -> list[CheckResult]:
    """Evaluate deterministic checks. No model calls or network access are made."""
    if not isinstance(response, str):
        response = ""
    results: list[CheckResult] = []

    for phrase in checks.get("must_contain", []):
        found = phrase.casefold() in response.casefold()
        results.append(CheckResult(f"must_contain:{phrase}", found, "found" if found else "missing"))

    for phrase in checks.get("must_not_contain", []):
        found = phrase.casefold() not in response.casefold()
        results.append(CheckResult(f"must_not_contain:{phrase}", found, "absent" if found else "found"))

    min_chars = checks.get("min_chars")
    if min_chars is not None:
        passed = len(response.strip()) >= int(min_chars)
        results.append(CheckResult("min_chars", passed, f"{len(response.strip())} >= {min_chars}" if passed else f"{len(response.strip())} < {min_chars}"))

    max_words = checks.get("max_words")
    if max_words is not None:
        count = len(re.findall(r"\\b[\\w'-]+\\b", response, flags=re.UNICODE))
        passed = count <= int(max_words)
        results.append(CheckResult("max_words", passed, f"{count} <= {max_words}" if passed else f"{count} > {max_words}"))

    if checks.get("valid_json", False):
        try:
            json.loads(response)
            results.append(CheckResult("valid_json", True, "valid JSON"))
        except (json.JSONDecodeError, TypeError):
            results.append(CheckResult("valid_json", False, "invalid JSON"))

    return results


def summarize(results: list[CheckResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(item.passed for item in results)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success": passed == total,
        "checks": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
    }
