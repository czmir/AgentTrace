from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agenttrace.core import SpanKind, TokenUsage
from agenttrace.session import get_current_session


class OpenAITraceMiddleware:
    """Wrap OpenAI-compatible chat completion calls with model spans."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def chat_completions_create(self, *args: Any, **kwargs: Any) -> Any:
        session = get_current_session()
        messages = kwargs.get("messages") or (args[0] if args else None)
        tools = kwargs.get("tools")
        if session is None:
            return self._client.chat.completions.create(*args, **kwargs)

        with session.span(
            kwargs.get("model", "chat.completions"),
            SpanKind.MODEL,
            input={"messages": messages, "tools": tools},
            attributes={"provider": "openai_compatible"},
        ) as span:
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(*args, **kwargs)
            except Exception as e:
                session.end_span(span, error=str(e))
                raise
            latency_ms = (time.time() - t0) * 1000
            usage = getattr(resp, "usage", None)
            tokens = TokenUsage()
            if usage:
                tokens = TokenUsage(
                    prompt=getattr(usage, "prompt_tokens", 0) or 0,
                    completion=getattr(usage, "completion_tokens", 0) or 0,
                    total=getattr(usage, "total_tokens", 0) or 0,
                )
            content = None
            if resp.choices:
                content = resp.choices[0].message
            session.end_span(
                span,
                output={"content": str(content), "latency_ms": latency_ms},
                tokens=tokens,
            )
            return resp


def wrap_callable(name: str, fn: Callable[..., Any], kind: SpanKind = SpanKind.TOOL) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        session = get_current_session()
        if session is None:
            return fn(*args, **kwargs)
        with session.span(name, kind, input={"args": args, "kwargs": kwargs}) as span:
            result = fn(*args, **kwargs)
            span.output = result
            return result

    return wrapped