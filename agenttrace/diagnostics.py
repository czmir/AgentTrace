from __future__ import annotations

from collections import Counter
from typing import Any

from agenttrace.core import SpanKind, Trace


class DiagnosticFinding:
    def __init__(self, code: str, message: str, *, span_id: str | None = None, severity: str = "warning"):
        self.code = code
        self.message = message
        self.span_id = span_id
        self.severity = severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "span_id": self.span_id,
            "severity": self.severity,
        }


def analyze_trace(trace: Trace, *, context_token_limit: int = 128_000) -> list[DiagnosticFinding]:
    findings: list[DiagnosticFinding] = []

    tool_failures = [s for s in trace.spans if s.kind == SpanKind.TOOL and s.error]
    for s in tool_failures:
        findings.append(
            DiagnosticFinding(
                "tool_failure",
                f"Tool '{s.name}' failed: {s.error}",
                span_id=s.id,
                severity="error",
            )
        )

    model_spans = [s for s in trace.spans if s.kind == SpanKind.MODEL]
    total_prompt = sum(s.tokens.prompt for s in model_spans)
    if total_prompt > context_token_limit:
        findings.append(
            DiagnosticFinding(
                "context_overflow",
                f"Estimated prompt tokens {total_prompt} exceed limit {context_token_limit}",
                severity="error",
            )
        )
    elif total_prompt > int(context_token_limit * 0.85):
        findings.append(
            DiagnosticFinding(
                "context_near_limit",
                f"Prompt tokens {total_prompt} above 85% of limit",
                severity="warning",
            )
        )

    names = [s.name for s in trace.spans]
    counts = Counter(names)
    for name, n in counts.items():
        if n >= 4 and name not in ("agent_loop",):
            findings.append(
                DiagnosticFinding(
                    "possible_loop",
                    f"Span '{name}' repeated {n} times — possible loop",
                    severity="warning",
                )
            )

    for s in trace.spans:
        if s.kind == SpanKind.TOOL and s.error and "timeout" in (s.error or "").lower():
            findings.append(
                DiagnosticFinding("tool_timeout", s.error, span_id=s.id, severity="error")
            )
        attrs = s.attributes or {}
        if attrs.get("invalid_params"):
            findings.append(
                DiagnosticFinding(
                    "bad_params",
                    f"Invalid parameters on '{s.name}': {attrs.get('invalid_params')}",
                    span_id=s.id,
                    severity="error",
                )
            )

    if trace.status.value == "error" and not tool_failures:
        err_spans = [s for s in trace.spans if s.error]
        if err_spans:
            findings.append(
                DiagnosticFinding(
                    "execution_error",
                    err_spans[-1].error or "unknown error",
                    span_id=err_spans[-1].id,
                    severity="error",
                )
            )

    return findings