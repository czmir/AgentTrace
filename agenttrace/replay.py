"""Replay: history reconstruction vs real re-execute.

History replay copies stored I/O into a new trace and never calls handlers.
Re-execute calls a HandlerRegistry, honors version bind, side-effect limits,
and human confirmation.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from agenttrace.core import Span, SpanKind, Trace, TraceStatus
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession


class ReplayMode(str, Enum):
    HISTORY = "history"
    REEXECUTE = "reexecute"


class ReplayBlocked(RuntimeError):
    """Re-execute refused (missing handler, version mismatch, side-effect, human)."""


class HandlerSpec:
    def __init__(
        self,
        name: str,
        handler: Callable[[Any], Any],
        *,
        version: str | None = None,
        side_effects: bool = False,
        requires_confirm: bool = False,
        kind: SpanKind | None = None,
    ) -> None:
        self.name = name
        self.handler = handler
        self.version = version
        self.side_effects = side_effects
        self.requires_confirm = requires_confirm
        self.kind = kind


class HandlerRegistry:
    """Name → handler with version / side-effect / confirm metadata."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerSpec] = {}

    def register(
        self,
        name: str,
        handler: Callable[[Any], Any],
        *,
        version: str | None = None,
        side_effects: bool = False,
        requires_confirm: bool = False,
        kind: SpanKind | None = None,
    ) -> None:
        self._handlers[name] = HandlerSpec(
            name,
            handler,
            version=version,
            side_effects=side_effects,
            requires_confirm=requires_confirm,
            kind=kind,
        )

    def get(self, name: str) -> HandlerSpec | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return sorted(self._handlers)

    def __contains__(self, name: str) -> bool:
        return name in self._handlers


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
        "output": copy.deepcopy(span.output),
        "error": span.error,
    }


def _confirm_ok(confirm: bool | Callable[[Span], bool], span: Span) -> bool:
    if callable(confirm):
        return bool(confirm(span))
    return bool(confirm)


class ReplayController:
    """History replay (no side effects) vs real re-execute with a registry."""

    def __init__(self, delay_ms: float = 0) -> None:
        self.delay_ms = delay_ms

    def replay_history(
        self,
        trace: Trace,
        *,
        recorder: TraceRecorder | None = None,
        span_id: str | None = None,
    ) -> Trace:
        """Reconstruct stored I/O. Does not call handlers. Not a re-execute."""
        spans = self._select_spans(trace, span_id)
        meta = {
            "replay_of": trace.id,
            "replay_mode": ReplayMode.HISTORY.value,
            "source_span": span_id,
        }
        with TraceSession(f"history_replay:{trace.id}", recorder=recorder, metadata=meta) as session:
            span_ids: dict[str, str] = {}
            offset_ns = time.time_ns() - spans[0].start_ns if spans else 0
            for src in spans:
                if self.delay_ms:
                    time.sleep(self.delay_ms / 1000)
                span = Span(
                    trace_id=session.trace.id,
                    parent_id=span_ids.get(src.parent_id) if src.parent_id else None,
                    **src.model_copy(deep=True).model_dump(
                        exclude={"id", "trace_id", "parent_id", "start_ns", "end_ns"},
                    ),
                    start_ns=src.start_ns + offset_ns,
                    end_ns=src.end_ns + offset_ns if src.end_ns is not None else None,
                )
                span_ids[src.id] = span.id
                session.trace.add_span(span)
                if span.parent_id is None and session.trace.root_span_id is None:
                    session.trace.root_span_id = span.id
            session.trace.finish(trace.status)
        return session.trace

    def reexecute(
        self,
        trace: Trace,
        registry: HandlerRegistry,
        *,
        recorder: TraceRecorder | None = None,
        span_id: str | None = None,
        allow_side_effects: bool = False,
        confirm: bool | Callable[[Span], bool] = False,
        bind_version: str | None = None,
        skip_missing: bool = False,
    ) -> Trace:
        """Call registered handlers. Blocked on version / side-effect / human unless allowed."""
        spans = self._select_spans(trace, span_id)
        meta = {
            "replay_of": trace.id,
            "replay_mode": ReplayMode.REEXECUTE.value,
            "bind_version": bind_version,
            "allow_side_effects": allow_side_effects,
            "source_span": span_id,
        }
        blocked: list[str] = []
        handler_failed = False
        with TraceSession(f"reexecute:{trace.id}", recorder=recorder, metadata=meta) as session:
            for src in spans:
                if self.delay_ms:
                    time.sleep(self.delay_ms / 1000)
                spec = registry.get(src.name)
                needs_confirm = src.kind == SpanKind.HUMAN or (spec is not None and spec.requires_confirm)
                attrs = dict(src.attributes or {})
                if spec is None:
                    msg = f"no handler registered for {src.name!r}"
                    if skip_missing:
                        with session.span(src.name, src.kind, input=src.input, attributes={**attrs, "skipped": "no_handler"}):
                            pass
                        continue
                    blocked.append(msg)
                    with session.span(src.name, src.kind, input=src.input) as span:
                        session.end_span(span, error=msg)
                    continue
                if bind_version is not None and spec.version != bind_version:
                    msg = (
                        f"version bind failed for {src.name!r}: "
                        f"handler={spec.version!r} required={bind_version!r}"
                    )
                    blocked.append(msg)
                    with session.span(src.name, src.kind, input=src.input) as span:
                        session.end_span(span, error=msg)
                    continue
                if spec.side_effects and not allow_side_effects:
                    msg = f"side-effect handler {src.name!r} blocked (allow_side_effects=False)"
                    blocked.append(msg)
                    with session.span(
                        src.name, src.kind, input=src.input, attributes={**attrs, "skipped": "side_effect"}
                    ) as span:
                        session.end_span(span, error=msg)
                    continue
                if needs_confirm and not _confirm_ok(confirm, src):
                    msg = f"human confirmation required for {src.name!r}"
                    blocked.append(msg)
                    with session.span(
                        src.name, src.kind, input=src.input, attributes={**attrs, "skipped": "human_confirm"}
                    ) as span:
                        session.end_span(span, error=msg)
                    continue
                with session.span(src.name, src.kind, input=src.input, attributes=attrs) as span:
                    try:
                        span.output = spec.handler(src.input)
                    except Exception as e:
                        session.end_span(span, error=str(e))
                        handler_failed = True
            if blocked or handler_failed:
                session.trace.finish(TraceStatus.ERROR)
            if blocked:
                session.trace.metadata["replay_blocked"] = blocked
        return session.trace

    def replay_trace(
        self,
        trace: Trace,
        handlers: dict[str, Callable[[Any], Any]],
        *,
        recorder: TraceRecorder | None = None,
    ) -> Trace:
        """Backward-compatible re-execute from a plain name→callable map."""
        registry = HandlerRegistry()
        for name, fn in handlers.items():
            registry.register(name, fn)
        return self.reexecute(trace, registry, recorder=recorder, skip_missing=True)

    @staticmethod
    def _select_spans(trace: Trace, span_id: str | None) -> list[Span]:
        if span_id is None:
            return sorted(trace.spans, key=lambda s: s.start_ns)
        span = trace.span_by_id(span_id)
        if span is None:
            raise ValueError(f"Span {span_id} not found")
        return [span]


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
    with (
        TraceSession(
            name,
            recorder=recorder,
            metadata={
                "replay_of": trace.id,
                "source_span": span_id,
                "replay_mode": ReplayMode.REEXECUTE.value,
            },
        ) as session,
        session.span(f"replay_{node['name']}", SpanKind(node["kind"]), input=node["input"]) as span,
    ):
        try:
            result = handler(node)
            span.output = result
        except Exception as e:
            session.end_span(span, error=str(e))
            raise
    return session.trace
