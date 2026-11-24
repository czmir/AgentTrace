from __future__ import annotations

from typing import Any

from agenttrace.core import SpanKind, Trace


def analyze_context(trace: Trace) -> dict[str, Any]:
    """Summarize per-model-call context composition and token distribution."""
    model_spans = [s for s in trace.spans if s.kind == SpanKind.MODEL]
    if not model_spans:
        return {"model_calls": 0, "calls": []}

    calls: list[dict[str, Any]] = []
    for s in sorted(model_spans, key=lambda x: x.start_ns):
        inp = s.input if isinstance(s.input, dict) else {}
        messages = inp.get("messages") or []
        tools = inp.get("tools") or inp.get("tool_definitions") or []
        calls.append(
            {
                "span_id": s.id,
                "name": s.name,
                "message_count": len(messages) if isinstance(messages, list) else 0,
                "tool_definition_count": len(tools) if isinstance(tools, list) else 0,
                "tokens": s.tokens.model_dump(),
                "roles": _role_distribution(messages),
            }
        )

    total_prompt = sum(c["tokens"]["prompt"] for c in calls)
    total_completion = sum(c["tokens"]["completion"] for c in calls)
    return {
        "model_calls": len(calls),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "calls": calls,
    }


def _role_distribution(messages: Any) -> dict[str, int]:
    if not isinstance(messages, list):
        return {}
    out: dict[str, int] = {}
    for m in messages:
        if isinstance(m, dict):
            role = str(m.get("role", "unknown"))
            out[role] = out.get(role, 0) + 1
    return out