"""Redact secrets, auth material, and sensitive fields before traces are persisted."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# Field names commonly used for credentials / PII-bearing auth.
_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|auth(orization)?|secret|password|passwd|passphrase|"
    r"access[_-]?token|refresh[_-]?token|id[_-]?token|private[_-]?key|"
    r"credential|cookie|set-cookie|session[_-]?id|x[_-]?api[_-]?key)",
    re.IGNORECASE,
)

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-+=/]+", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


def redact_string(value: str) -> str:
    out = value
    for pat in _PATTERNS:
        out = pat.sub(REDACTED, out)
    return out


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return _SENSITIVE_KEY.search(key) is not None


def redact_value(value: Any) -> Any:
    """Return a redacted copy of nested JSON-like data. Does not fake or drop traces."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                out[k] = REDACTED
            else:
                out[k] = redact_value(v)
        return out
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v) for v in value)
    if isinstance(value, bytes):
        try:
            return redact_string(value.decode("utf-8", errors="replace"))
        except Exception:
            return REDACTED
    return value


def redact_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact span I/O, errors, attributes, and trace metadata. Keep structure intact."""
    data = redact_value(payload)
    if not isinstance(data, dict):
        return payload
    return data
