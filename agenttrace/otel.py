from __future__ import annotations

from typing import Any

from agenttrace.core import Span, Trace


def export_trace_to_otel_spans(trace: Trace) -> list[dict[str, Any]]:
    """Map AgentTrace spans to OTLP-like dicts for external collectors."""
    out = []
    for s in trace.spans:
        out.append(
            {
                "trace_id": trace.id,
                "span_id": s.id,
                "parent_span_id": s.parent_id,
                "name": s.name,
                "kind": s.kind.value,
                "start_time_unix_nano": s.start_ns,
                "end_time_unix_nano": s.end_ns,
                "attributes": {
                    **(s.attributes or {}),
                    "agenttrace.tokens.prompt": s.tokens.prompt,
                    "agenttrace.tokens.completion": s.tokens.completion,
                },
                "status": "ERROR" if s.error else "OK",
            }
        )
    return out


def configure_otel_exporter(service_name: str = "agenttrace") -> Any | None:
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        otel_trace.set_tracer_provider(provider)
        return otel_trace.get_tracer("agenttrace")
    except Exception:
        return None