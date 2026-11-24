from __future__ import annotations

from typing import Any, Callable, TypeVar

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session

F = TypeVar("F", bound=Callable[..., Any])


def wrap_langgraph_node(name: str) -> Callable[[F], F]:
    """Decorator for LangGraph node functions — records workflow spans."""

    def decorator(fn: F) -> F:
        def wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return fn(state, *args, **kwargs)
            with session.span(f"node:{name}", SpanKind.WORKFLOW, input={"state_keys": list(state.keys())}) as span:
                out = fn(state, *args, **kwargs)
                span.output = {"state_keys": list(out.keys()) if isinstance(out, dict) else type(out).__name__}
                return out

        wrapper.__name__ = fn.__name__
        return wrapper  # type: ignore

    return decorator