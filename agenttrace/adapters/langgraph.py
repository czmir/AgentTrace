from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session

F = TypeVar("F", bound=Callable[..., Any])


def wrap_langgraph_node(name: str) -> Callable[[F], F]:
    """Decorator for LangGraph node functions — records workflow spans (sync or async)."""

    def decorator(fn: F) -> F:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
                session = get_current_session()
                if session is None:
                    return await fn(state, *args, **kwargs)
                keys = list(state.keys()) if isinstance(state, dict) else type(state).__name__
                async with session.aspan(
                    f"node:{name}", SpanKind.WORKFLOW, input={"state_keys": keys}
                ) as span:
                    out = await fn(state, *args, **kwargs)
                    span.output = {
                        "state_keys": list(out.keys()) if isinstance(out, dict) else type(out).__name__
                    }
                    return out

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return fn(state, *args, **kwargs)
            keys = list(state.keys()) if isinstance(state, dict) else type(state).__name__
            with session.span(f"node:{name}", SpanKind.WORKFLOW, input={"state_keys": keys}) as span:
                out = fn(state, *args, **kwargs)
                span.output = {
                    "state_keys": list(out.keys()) if isinstance(out, dict) else type(out).__name__
                }
                return out

        return wrapper  # type: ignore[return-value]

    return decorator
