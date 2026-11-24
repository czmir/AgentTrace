from __future__ import annotations

from typing import Any
from uuid import UUID

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session


class AgentTraceHandler:
    """Minimal LangChain-style callback handler (no hard dependency on langchain)."""

    def __init__(self) -> None:
        self._run_map: dict[str, Any] = {}

    def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        session = get_current_session()
        if not session:
            return
        name = serialized.get("name") or serialized.get("id", ["chain"])[-1]
        span = session.start_span(str(name), SpanKind.WORKFLOW, input=inputs)
        self._run_map[str(run_id)] = span

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, output=outputs)

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        session = get_current_session()
        if not session:
            return
        name = serialized.get("name", "tool")
        span = session.start_span(name, SpanKind.TOOL, input={"input": input_str})
        self._run_map[str(run_id)] = span

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, output=output)

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs: Any) -> None:
        session = get_current_session()
        if not session:
            return
        name = serialized.get("name", "llm")
        span = session.start_span(name, SpanKind.MODEL, input={"prompts": prompts})
        self._run_map[str(run_id)] = span

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, output=str(response))