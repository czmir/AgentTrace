from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SpanKind(str, Enum):
    MODEL = "model"
    TOOL = "tool"
    WORKFLOW = "workflow"
    SKILL = "skill"
    HUMAN = "human"
    MCP = "mcp"


class TraceStatus(str, Enum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class Span(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str
    parent_id: str | None = None
    name: str
    kind: SpanKind = SpanKind.WORKFLOW
    start_ns: int = Field(default_factory=time.time_ns)
    end_ns: int | None = None
    input: Any = None
    output: Any = None
    error: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tokens: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def duration_ms(self) -> float | None:
        if self.end_ns is None:
            return None
        return (self.end_ns - self.start_ns) / 1_000_000

    def finish(
        self,
        output: Any = None,
        *,
        error: str | None = None,
        tokens: TokenUsage | None = None,
    ) -> None:
        self.end_ns = time.time_ns()
        if output is not None:
            self.output = output
        if error is not None:
            self.error = error
        if tokens is not None:
            self.tokens = tokens

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Trace(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    status: TraceStatus = TraceStatus.RUNNING
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    spans: list[Span] = Field(default_factory=list)
    root_span_id: str | None = None

    def add_span(self, span: Span) -> None:
        self.spans.append(span)

    def span_by_id(self, span_id: str) -> Span | None:
        for s in self.spans:
            if s.id == span_id:
                return s
        return None

    def finish(self, status: TraceStatus = TraceStatus.OK) -> None:
        self.status = status
        self.ended_at = time.time()

    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000

    def tree(self) -> list[dict[str, Any]]:
        by_parent: dict[str | None, list[Span]] = {}
        for span in self.spans:
            by_parent.setdefault(span.parent_id, []).append(span)

        def build(parent_id: str | None) -> list[dict[str, Any]]:
            nodes = []
            for s in sorted(by_parent.get(parent_id, []), key=lambda x: x.start_ns):
                nodes.append(
                    {
                        "span": s.to_dict(),
                        "children": build(s.id),
                    }
                )
            return nodes

        return build(None)

    def timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind.value,
                "start_ns": s.start_ns,
                "end_ns": s.end_ns,
                "duration_ms": s.duration_ms,
                "error": s.error,
            }
            for s in sorted(self.spans, key=lambda x: x.start_ns)
        ]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")