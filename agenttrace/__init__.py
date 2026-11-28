"""AgentTrace — lightweight agent execution tracing, debugging, and eval."""

from agenttrace.core import Span, SpanKind, Trace, TraceStatus
from agenttrace.decorators import trace_span
from agenttrace.recorder import TraceRecorder
from agenttrace.replay import HandlerRegistry, ReplayController, ReplayMode
from agenttrace.session import TraceSession, get_current_session, get_current_span_id

__version__ = "0.3.0"
__all__ = [
    "HandlerRegistry",
    "ReplayController",
    "ReplayMode",
    "Span",
    "SpanKind",
    "Trace",
    "TraceRecorder",
    "TraceSession",
    "TraceStatus",
    "get_current_session",
    "get_current_span_id",
    "trace_span",
]
