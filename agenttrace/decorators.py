from __future__ import annotations

import functools
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
    """Decorator that records a span in the active TraceSession."""

    def decorator(fn: F) -> F:
        span_name = name or fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            session = get_current_session()
            if session is None:
                return fn(*args, **kwargs)
            inp = {"args": args, "kwargs": kwargs} if capture_input else None
            span = session.start_span(span_name, kind, input=inp)
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                session.end_span(span, error=str(e))
                raise
            out = result if capture_output else None
            session.end_span(span, output=out)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator