from __future__ import annotations

from typing import Any
from uuid import UUID

from agenttrace.core import Span, SpanKind, TokenUsage
from agenttrace.session import get_current_session


class AgentTraceHandler:
    """LangChain-style callback handler (no hard dependency on langchain).

    Works as a BaseCallbackHandler duck-type: pass via config={"callbacks": [handler]}.
    """

    def __init__(self) -> None:
        self._run_map: dict[str, Span] = {}

    def _parent_id(self, kwargs: dict[str, Any]) -> str | None:
        parent_run_id = kwargs.get("parent_run_id")
        if not parent_run_id:
            return None
        parent = self._run_map.get(str(parent_run_id))
        return parent.id if parent is not None else None

    def on_chain_start(
        self, serialized: dict[str, Any] | None, inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        session = get_current_session()
        if not session:
            return
        serialized = serialized or {}
        name = serialized.get("name") or (serialized.get("id") or ["chain"])[-1]
        span = session.start_span(
            str(name), SpanKind.WORKFLOW, input=inputs, parent_id=self._parent_id(kwargs)
        )
        self._run_map[str(run_id)] = span

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, output=outputs)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, error=str(error))

    def on_tool_start(
        self, serialized: dict[str, Any] | None, input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        session = get_current_session()
        if not session:
            return
        serialized = serialized or {}
        name = serialized.get("name", "tool")
        span = session.start_span(
            name, SpanKind.TOOL, input={"input": input_str}, parent_id=self._parent_id(kwargs)
        )
        self._run_map[str(run_id)] = span

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, output=output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, error=str(error))

    def on_llm_start(
        self, serialized: dict[str, Any] | None, prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        session = get_current_session()
        if not session:
            return
        serialized = serialized or {}
        name = serialized.get("name", "llm")
        span = session.start_span(
            name, SpanKind.MODEL, input={"prompts": prompts}, parent_id=self._parent_id(kwargs)
        )
        self._run_map[str(run_id)] = span

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            tokens = _tokens_from_llm_response(response)
            session.end_span(span, output=_llm_output(response), tokens=tokens)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._run_map.pop(str(run_id), None)
        session = get_current_session()
        if span and session:
            session.end_span(span, error=str(error))

    async def aon_chain_start(self, *args: Any, **kwargs: Any) -> None:
        self.on_chain_start(*args, **kwargs)

    async def aon_chain_end(self, *args: Any, **kwargs: Any) -> None:
        self.on_chain_end(*args, **kwargs)

    async def aon_chain_error(self, *args: Any, **kwargs: Any) -> None:
        self.on_chain_error(*args, **kwargs)

    async def aon_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self.on_tool_start(*args, **kwargs)

    async def aon_tool_end(self, *args: Any, **kwargs: Any) -> None:
        self.on_tool_end(*args, **kwargs)

    async def aon_tool_error(self, *args: Any, **kwargs: Any) -> None:
        self.on_tool_error(*args, **kwargs)

    async def aon_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.on_llm_start(*args, **kwargs)

    async def aon_llm_end(self, *args: Any, **kwargs: Any) -> None:
        self.on_llm_end(*args, **kwargs)

    async def aon_llm_error(self, *args: Any, **kwargs: Any) -> None:
        self.on_llm_error(*args, **kwargs)


def _llm_output(response: Any) -> Any:
    gens = getattr(response, "generations", None)
    if gens:
        try:
            return str(gens[0][0].text)
        except Exception:
            return str(response)
    return str(response)


def _tokens_from_llm_response(response: Any) -> TokenUsage | None:
    llm_output = getattr(response, "llm_output", None) or {}
    if not isinstance(llm_output, dict):
        return None
    usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if not usage:
        return None
    return TokenUsage(
        prompt=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        completion=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        total=int(usage.get("total_tokens") or 0),
    )
