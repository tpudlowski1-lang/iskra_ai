"""Best-effort outbound prompt minimization for common secret/PII patterns.

This is a defense-in-depth filter, not a complete DLP scanner or compliance control.
"""
import re


_PATTERNS = (
    (re.compile(r"""-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"""), "[REDACTED:PRIVATE_KEY]"),
    (re.compile(r"""(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"""), "[REDACTED:BEARER_TOKEN]"),
    (re.compile(r"""\bgithub_pat_[A-Za-z0-9_]{20,}\b"""), "[REDACTED:ACCESS_TOKEN]"),
    (re.compile(r"""\bgh[pousr]_[A-Za-z0-9]{20,}\b"""), "[REDACTED:ACCESS_TOKEN]"),
    (re.compile(r"""\bxox[baprs]-[A-Za-z0-9-]{10,}\b"""), "[REDACTED:ACCESS_TOKEN]"),
    (re.compile(r"""\bAKIA[0-9A-Z]{16}\b"""), "[REDACTED:CLOUD_KEY]"),
    (re.compile(r"""\bsk-[A-Za-z0-9_-]{20,}\b"""), "[REDACTED:API_KEY]"),
    (re.compile(r"""(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret)\b\s*[:=]\s*["']?[^\s"',;}{]{6,}"""), "[REDACTED:SECRET_FIELD]"),
    (re.compile(r"""\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"""), "[REDACTED:JWT]"),
    (re.compile(r"""(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"""), "[REDACTED:EMAIL]"),
    (re.compile(r"""\b[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]){11,30}\b"""), "[REDACTED:IBAN]"),
)


def minimize_outbound_text(value):
    """Redact common high-risk patterns from text before external inference."""
    if not isinstance(value, str):
        raise TypeError("Tekst do minimalizacji musi być typu str")
    result = value
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result
