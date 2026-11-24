from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session

F = TypeVar("F", bound=Callable[..., Any])


def trace_mcp_tool_call(server: str, tool_name: str) -> Callable[[F], F]:
    """Wrap MCP tool invocations with MCP-kind spans."""

    def decorator(fn: F) -> F:
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
                try:
                    result = fn(*args, **kwargs)
                except Exception as e:
                    session.end_span(span, error=str(e))
                    raise
                session.end_span(span, output=result)
                return result

        return wrapper  # type: ignore

    return decorator