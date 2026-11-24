from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator

from agenttrace.core import Span, SpanKind, Trace, TraceStatus, TokenUsage
from agenttrace.recorder import TraceRecorder

_current_session: contextvars.ContextVar[TraceSession | None] = contextvars.ContextVar(
    "agenttrace_session", default=None
)


def get_current_session() -> TraceSession | None:
    return _current_session.get()


class TraceSession:
    """Active tracing session bound to a Trace and optional recorder."""

    def __init__(
        self,
        name: str,
        *,
        recorder: TraceRecorder | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace = Trace(name=name, metadata=metadata or {})
        self.recorder = recorder
        self._span_stack: list[str] = []
        self._token = None

    def __enter__(self) -> TraceSession:
        self._token = _current_session.set(self)
        if self.recorder:
            self.recorder.save_trace(self.trace)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.trace.status == TraceStatus.RUNNING:
            if exc:
                self.trace.finish(TraceStatus.ERROR)
            else:
                self.trace.finish(TraceStatus.OK)
        if self.recorder:
            self.recorder.save_trace(self.trace)
            self.recorder.emit_event(
                "trace_finished",
                {"trace_id": self.trace.id, "status": self.trace.status.value},
            )
        if self._token is not None:
            _current_session.reset(self._token)

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.WORKFLOW,
        *,
        parent_id: str | None = None,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        parent = parent_id
        if parent is None and self._span_stack:
            parent = self._span_stack[-1]
        span = Span(
            trace_id=self.trace.id,
            parent_id=parent,
            name=name,
            kind=kind,
            input=input,
            attributes=attributes or {},
        )
        self.trace.add_span(span)
        if self.trace.root_span_id is None and parent is None:
            self.trace.root_span_id = span.id
        self._span_stack.append(span.id)
        if self.recorder:
            self.recorder.save_trace(self.trace)
            self.recorder.emit_event(
                "span_started",
                {"trace_id": self.trace.id, "span_id": span.id, "name": name},
            )
        return span

    def end_span(
        self,
        span: Span,
        *,
        output: Any = None,
        error: str | None = None,
        tokens: TokenUsage | None = None,
    ) -> None:
        span.finish(output=output, error=error, tokens=tokens)
        if span.id in self._span_stack:
            while self._span_stack and self._span_stack[-1] != span.id:
                self._span_stack.pop()
            if self._span_stack and self._span_stack[-1] == span.id:
                self._span_stack.pop()
        if self.recorder:
            self.recorder.save_trace(self.trace)
            self.recorder.emit_event(
                "span_finished",
                {
                    "trace_id": self.trace.id,
                    "span_id": span.id,
                    "error": error,
                    "duration_ms": span.duration_ms,
                },
            )

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.WORKFLOW,
        *,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Span]:
        s = self.start_span(name, kind, input=input, attributes=attributes)
        try:
            yield s
        except Exception as e:
            self.end_span(s, error=str(e))
            raise
        else:
            self.end_span(s, output=s.output)