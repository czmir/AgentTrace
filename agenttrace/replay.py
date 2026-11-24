from __future__ import annotations

import copy
import time
from typing import Any, Callable

from agenttrace.core import Span, SpanKind, Trace, TokenUsage
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession


def extract_node_inputs(trace: Trace, span_id: str) -> dict[str, Any] | None:
    span = trace.span_by_id(span_id)
    if not span:
        return None
    return {
        "span_id": span.id,
        "name": span.name,
        "kind": span.kind.value,
        "input": copy.deepcopy(span.input),
        "attributes": copy.deepcopy(span.attributes),
    }


def rerun_node(
    trace: Trace,
    span_id: str,
    handler: Callable[[dict[str, Any]], Any],
    *,
    recorder: TraceRecorder | None = None,
    session_name: str | None = None,
) -> Trace:
    """Re-execute a single node with stored input under a new replay trace."""
    node = extract_node_inputs(trace, span_id)
    if node is None:
        raise ValueError(f"Span {span_id} not found")

    name = session_name or f"replay:{trace.name}:{node['name']}"
    with TraceSession(name, recorder=recorder, metadata={"replay_of": trace.id, "source_span": span_id}) as session:
        with session.span(
            f"replay_{node['name']}", SpanKind(node["kind"]), input=node["input"]
        ) as span:
            try:
                result = handler(node)
                span.output = result
            except Exception as e:
                session.end_span(span, error=str(e))
                raise
    return session.trace


class ReplayController:
    """Controlled replay with optional step delay (for demos/tests)."""

    def __init__(self, delay_ms: float = 0) -> None:
        self.delay_ms = delay_ms

    def replay_trace(
        self,
        trace: Trace,
        handlers: dict[str, Callable[[Any], Any]],
        *,
        recorder: TraceRecorder | None = None,
    ) -> Trace:
        ordered = sorted(trace.spans, key=lambda s: s.start_ns)
        with TraceSession(f"full_replay:{trace.id}", recorder=recorder, metadata={"replay_of": trace.id}) as session:
            for src in ordered:
                if self.delay_ms:
                    time.sleep(self.delay_ms / 1000)
                handler = handlers.get(src.name)
                if not handler:
                    continue
                with session.span(src.name, src.kind, input=src.input) as span:
                    try:
                        span.output = handler(src.input)
                    except Exception as e:
                        session.end_span(span, error=str(e))
        return session.trace