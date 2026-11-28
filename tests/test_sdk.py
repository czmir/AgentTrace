from agenttrace import TraceSession, trace_span
from agenttrace.core import SpanKind, TraceStatus
from agenttrace.diagnostics import analyze_trace
from agenttrace.recorder import TraceRecorder


def test_open_session_is_readable_from_another_recorder(tmp_path):
    path = tmp_path / "live.db"
    writer = TraceRecorder(path)
    reader = TraceRecorder(path)
    with TraceSession("partial", recorder=writer) as session:
        with session.span("root") as root:
            with session.span("tool") as child:
                child.output = {"result": "ok"}
            live = reader.get_trace(session.trace.id)
            assert live.root_span_id == root.id
            assert live.spans[0].end_ns is None
            assert live.spans[1].parent_id == root.id
            assert live.spans[1].output == {"result": "ok"}
    finished = reader.get_trace(session.trace.id)
    assert [span.id for span in finished.spans] == [root.id, child.id]
    assert finished.spans[0].end_ns is not None


def test_trace_session_tree(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with (
        TraceSession("test", recorder=rec) as session,
        session.span("root", SpanKind.WORKFLOW) as root,
    ):
        root.output = 1
        with session.span("child", SpanKind.TOOL) as child:
            child.output = {"ok": True}
    tr = rec.get_trace(session.trace.id)
    assert tr is not None
    assert tr.status == TraceStatus.OK
    assert len(tr.spans) == 2
    tree = tr.tree()
    assert len(tree) == 1
    assert len(tree[0]["children"]) == 1


@trace_span("wrapped_fn", kind=SpanKind.TOOL)
def add(a: int, b: int) -> int:
    return a + b


def test_decorator_without_session():
    assert add(1, 2) == 3


def test_decorator_with_session(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("dec", recorder=rec):
        assert add(2, 3) == 5


def test_diagnostics_tool_failure(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("fail", recorder=rec) as session:
        with session.span("bad_tool", SpanKind.TOOL) as s:
            session.end_span(s, error="boom")
        session.trace.finish(TraceStatus.ERROR)
    tr = rec.get_trace(session.trace.id)
    findings = analyze_trace(tr)
    assert any(f.code == "tool_failure" for f in findings)
