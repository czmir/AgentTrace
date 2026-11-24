"""AgentTrace — lightweight agent execution tracing, debugging, and eval."""

from agenttrace.core import Span, SpanKind, Trace, TraceStatus
from agenttrace.decorators import trace_span
from agenttrace.session import TraceSession, get_current_session
from agenttrace.recorder import TraceRecorder

__version__ = "0.1.0"
__all__ = [
    "Span",
    "SpanKind",
    "Trace",
    "TraceStatus",
    "TraceSession",
    "TraceRecorder",
    "get_current_session",
    "trace_span",
]