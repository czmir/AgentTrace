from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session

F = TypeVar("F", bound=Callable[..., Any])


def trace_mcp_tool_call(server: str, tool_name: str) -> Callable[[F], F]:
    """Wrap MCP tool invocations with MCP-kind spans (sync or async)."""

    def decorator(fn: F) -> F:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                session = get_current_session()
                if session is None:
                    return await fn(*args, **kwargs)
                async with session.aspan(
                    f"mcp:{server}/{tool_name}",
                    SpanKind.MCP,
                    input={"args": args, "kwargs": kwargs},
                    attributes={"mcp_server": server, "tool": tool_name},
                ) as span:
                    result = await fn(*args, **kwargs)
                    span.output = result
                    return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return fn(*args, **kwargs)
            with session.span(
                f"mcp:{server}/{tool_name}",
                SpanKind.MCP,
                input={"args": args, "kwargs": kwargs},
                attributes={"mcp_server": server, "tool": tool_name},
            ) as span:
                result = fn(*args, **kwargs)
                span.output = result
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
