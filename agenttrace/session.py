from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Self

from agenttrace.core import Span, SpanKind, TokenUsage, Trace, TraceStatus
from agenttrace.recorder import TraceRecorder
from agenttrace.redact import redact_value

_current_session: contextvars.ContextVar[TraceSession | None] = contextvars.ContextVar(
    "agenttrace_session", default=None
)
_current_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agenttrace_span_id", default=None
)


def get_current_session() -> TraceSession | None:
    return _current_session.get()


def get_current_span_id() -> str | None:
    return _current_span_id.get()


class TraceSession:
    """Active tracing session bound to a Trace and optional recorder.

    Parent/child span links use contextvars so concurrent asyncio tasks do not
    share a process-wide stack (which previously mixed parents).
    """

    def __init__(
        self,
        name: str,
        *,
        recorder: TraceRecorder | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace = Trace(name=name, metadata=metadata or {})
        self.recorder = recorder
        self._token: contextvars.Token[TraceSession | None] | None = None
        self._span_tokens: dict[str, contextvars.Token[str | None]] = {}
        self._ended_spans: set[str] = set()

    def __enter__(self) -> Self:
        self._token = _current_session.set(self)
        if self.recorder:
            self.recorder.save_trace(self.trace)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._close(exc_type)

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._close(exc_type)

    def _close(self, exc_type: type[BaseException] | None) -> None:
        self._unwind_span_context()
        if self.trace.status == TraceStatus.RUNNING:
            if exc_type is None:
                self.trace.finish(TraceStatus.OK)
            elif issubclass(exc_type, asyncio.CancelledError):
                self.trace.finish(TraceStatus.CANCELLED)
            else:
                self.trace.finish(TraceStatus.ERROR)
        if self.recorder:
            self.recorder.save_trace(self.trace)
            self.recorder.emit_event(
                "trace_finished",
                {"trace_id": self.trace.id, "status": self.trace.status.value},
            )
        if self._token is not None:
            _current_session.reset(self._token)
            self._token = None

    def _unwind_span_context(self) -> None:
        """End leftover spans and drop ContextVar tokens so the next session is clean."""
        for sid in reversed(list(self._span_tokens)):
            span = self.trace.span_by_id(sid)
            if span is not None and sid not in self._ended_spans:
                self.end_span(span, error="session closed")
            else:
                token = self._span_tokens.pop(sid, None)
                if token is not None and _current_span_id.get() == sid:
                    _current_span_id.reset(token)

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.WORKFLOW,
        *,
        parent_id: str | None = None,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        parent = parent_id if parent_id is not None else _current_span_id.get()
        if parent is not None and self.trace.span_by_id(parent) is None:
            # Stale ContextVar from another session/task must not become parent.
            parent = None
        span = Span(
            trace_id=self.trace.id,
            parent_id=parent,
            name=name,
            kind=kind,
            input=redact_value(input),
            attributes=redact_value(attributes or {}) or {},
        )
        self.trace.add_span(span)
        if self.trace.root_span_id is None and parent is None:
            self.trace.root_span_id = span.id
        self._span_tokens[span.id] = _current_span_id.set(span.id)
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
        if span.id in self._ended_spans:
            return
        span.finish(
            output=redact_value(output) if output is not None else None,
            error=redact_value(error) if isinstance(error, str) else error,
            tokens=tokens,
        )
        self._ended_spans.add(span.id)
        token = self._span_tokens.pop(span.id, None)
        if token is not None and _current_span_id.get() == span.id:
            _current_span_id.reset(token)
        if self.recorder:
            self.recorder.save_trace(self.trace)
            self.recorder.emit_event(
                "span_finished",
                {
                    "trace_id": self.trace.id,
                    "span_id": span.id,
                    "error": span.error,
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
        except asyncio.CancelledError:
            self.end_span(s, error="cancelled")
            raise
        except Exception as e:
            self.end_span(s, error=str(e))
            raise
        else:
            self.end_span(s, output=s.output, tokens=s.tokens)

    @asynccontextmanager
    async def aspan(
        self,
        name: str,
        kind: SpanKind = SpanKind.WORKFLOW,
        *,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncIterator[Span]:
        s = self.start_span(name, kind, input=input, attributes=attributes)
        try:
            yield s
        except asyncio.CancelledError:
            self.end_span(s, error="cancelled")
            raise
        except Exception as e:
            self.end_span(s, error=str(e))
            raise
        else:
            self.end_span(s, output=s.output, tokens=s.tokens)
