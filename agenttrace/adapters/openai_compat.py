from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import Any

from agenttrace.core import SpanKind, TokenUsage
from agenttrace.session import get_current_session


class OpenAITraceMiddleware:
    """Wrap OpenAI-compatible chat completion calls with model spans (sync + async)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def chat_completions_create(self, *args: Any, **kwargs: Any) -> Any:
        return self._run_create(self._client.chat.completions.create, args, kwargs)

    async def achat_completions_create(self, *args: Any, **kwargs: Any) -> Any:
        create = self._client.chat.completions.create
        session = get_current_session()
        messages = kwargs.get("messages") or (args[0] if args else None)
        tools = kwargs.get("tools")
        if session is None:
            result = create(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        async with session.aspan(
            kwargs.get("model", "chat.completions"),
            SpanKind.MODEL,
            input={"messages": messages, "tools": tools},
            attributes={"provider": "openai_compatible"},
        ) as span:
            t0 = time.time()
            resp = create(*args, **kwargs)
            if inspect.isawaitable(resp):
                resp = await resp
            _fill_model_span(span, resp, t0)
            return resp

    def _run_create(self, create: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        session = get_current_session()
        messages = kwargs.get("messages") or (args[0] if args else None)
        tools = kwargs.get("tools")
        if session is None:
            return create(*args, **kwargs)

        with session.span(
            kwargs.get("model", "chat.completions"),
            SpanKind.MODEL,
            input={"messages": messages, "tools": tools},
            attributes={"provider": "openai_compatible"},
        ) as span:
            t0 = time.time()
            resp = create(*args, **kwargs)
            _fill_model_span(span, resp, t0)
            return resp


def _fill_model_span(span: Any, resp: Any, t0: float) -> None:
    latency_ms = (time.time() - t0) * 1000
    usage = getattr(resp, "usage", None)
    tokens = TokenUsage()
    if usage:
        tokens = TokenUsage(
            prompt=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion=int(getattr(usage, "completion_tokens", 0) or 0),
            total=int(getattr(usage, "total_tokens", 0) or 0),
        )
    content = None
    tool_calls = None
    choices = getattr(resp, "choices", None)
    if choices:
        message = choices[0].message
        content = getattr(message, "content", None)
        raw_calls = getattr(message, "tool_calls", None)
        if raw_calls:
            tool_calls = [str(c) for c in raw_calls]
    span.output = {"content": content, "tool_calls": tool_calls, "latency_ms": latency_ms}
    span.tokens = tokens


def wrap_callable(name: str, fn: Callable[..., Any], kind: SpanKind = SpanKind.TOOL) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(fn):

        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return await fn(*args, **kwargs)
            async with session.aspan(name, kind, input={"args": args, "kwargs": kwargs}) as span:
                result = await fn(*args, **kwargs)
                span.output = result
                return result

        return async_wrapped

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        session = get_current_session()
        if session is None:
            return fn(*args, **kwargs)
        with session.span(name, kind, input={"args": args, "kwargs": kwargs}) as span:
            result = fn(*args, **kwargs)
            span.output = result
            return result

    return wrapped
