"""AgentTrace — lightweight agent execution tracing, debugging, and eval."""

from agenttrace.core import Span, SpanKind, Trace, TraceStatus
from agenttrace.decorators import trace_span
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession, get_current_session

__version__ = "0.1.0"
__all__ = [
    "Span",
    "SpanKind",
    "Trace",
    "TraceRecorder",
    "TraceSession",
    "TraceStatus",
    "get_current_session",
    "trace_span",
]