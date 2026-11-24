from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from agenttrace.core import SpanKind
from agenttrace.session import get_current_session

F = TypeVar("F", bound=Callable[..., Any])


def trace_span(
    name: str | None = None,
    *,
    kind: SpanKind = SpanKind.WORKFLOW,
    capture_input: bool = True,
    capture_output: bool = True,
) -> Callable[[F], F]:
    """Decorator that records a span in the active TraceSession (sync or async)."""

    def decorator(fn: F) -> F:
        span_name = name or fn.__qualname__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                session = get_current_session()
                if session is None:
                    return await fn(*args, **kwargs)
                inp = {"args": args, "kwargs": kwargs} if capture_input else None
                async with session.aspan(span_name, kind, input=inp) as span:
                    result = await fn(*args, **kwargs)
                    if capture_output:
                        span.output = result
                    return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return fn(*args, **kwargs)
            inp = {"args": args, "kwargs": kwargs} if capture_input else None
            with session.span(span_name, kind, input=inp) as span:
                result = fn(*args, **kwargs)
                if capture_output:
                    span.output = result
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
