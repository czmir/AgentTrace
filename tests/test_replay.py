from agenttrace.core import SpanKind, TraceStatus
from agenttrace.recorder import TraceRecorder
from agenttrace.replay import HandlerRegistry, ReplayBlocked, ReplayController, ReplayMode
from agenttrace.session import TraceSession


def _sample(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("orig", recorder=rec) as session:
        with session.span("search_kb", SpanKind.TOOL, input={"q": "x"}) as s:
            s.output = {"hits": 1}
        with session.span("send_email", SpanKind.TOOL, input={"to": "a@b.c"}) as s:
            s.output = {"sent": True}
        with session.span("human_approval", SpanKind.HUMAN, input={"action": "send"}) as s:
            s.output = {"approved": True}
    return rec, rec.get_trace(session.trace.id)


def test_history_replay_does_not_call_handlers(tmp_path):
    rec, tr = _sample(tmp_path)
    called = []
    registry = HandlerRegistry()
    registry.register("search_kb", lambda inp: called.append("search") or inp)
    out = ReplayController().replay_history(tr, recorder=rec)
    assert out.metadata["replay_mode"] == ReplayMode.HISTORY.value
    assert called == []
    names = [s.name for s in out.spans]
    assert "search_kb" in names
    search = next(s for s in out.spans if s.name == "search_kb")
    assert search.output == {"hits": 1}


def test_reexecute_calls_handler(tmp_path):
    rec, tr = _sample(tmp_path)
    registry = HandlerRegistry()
    registry.register("search_kb", lambda inp: {"hits": 9, "echo": inp}, version="v1")
    registry.register("send_email", lambda inp: {"sent": True}, version="v1", side_effects=True)
    out = ReplayController().reexecute(
        tr, registry, recorder=rec, allow_side_effects=False, skip_missing=True
    )
    search = next(s for s in out.spans if s.name == "search_kb")
    assert search.output["hits"] == 9
    email = next(s for s in out.spans if s.name == "send_email")
    assert email.error and "side-effect" in email.error
    assert out.status == TraceStatus.ERROR


def test_version_bind(tmp_path):
    rec, tr = _sample(tmp_path)
    registry = HandlerRegistry()
    registry.register("search_kb", lambda inp: inp, version="v2")
    out = ReplayController().reexecute(
        tr, registry, recorder=rec, bind_version="v1", skip_missing=True
    )
    search = next(s for s in out.spans if s.name == "search_kb")
    assert search.error and "version bind" in search.error


def test_human_confirm_required(tmp_path):
    rec, tr = _sample(tmp_path)
    registry = HandlerRegistry()
    registry.register("human_approval", lambda inp: {"approved": True}, requires_confirm=True)
    out = ReplayController().reexecute(tr, registry, recorder=rec, confirm=False, skip_missing=True)
    human = next(s for s in out.spans if s.name == "human_approval")
    assert human.error and "confirmation" in human.error
    out2 = ReplayController().reexecute(tr, registry, recorder=rec, confirm=True, skip_missing=True)
    human2 = next(s for s in out2.spans if s.name == "human_approval")
    assert human2.error is None
    assert human2.output == {"approved": True}


def test_missing_handler_fails_without_skip(tmp_path):
    rec, tr = _sample(tmp_path)
    out = ReplayController().reexecute(tr, HandlerRegistry(), recorder=rec, skip_missing=False)
    assert out.status == TraceStatus.ERROR
    assert any("no handler" in (s.error or "") for s in out.spans)


def test_replay_blocked_type_exists():
    assert issubclass(ReplayBlocked, RuntimeError)


def test_history_replay_preserves_tree(tmp_path):
    rec = TraceRecorder(tmp_path / "history.db")
    with TraceSession("original") as session:
        with session.span("workflow"):
            with session.span("tool") as tool:
                tool.error = "failed"

    replay = ReplayController().replay_history(session.trace, recorder=rec)
    stored = rec.get_trace(replay.id)
    root, child = stored.spans
    assert (root.name, child.name) == ("workflow", "tool")
    assert stored.root_span_id == child.parent_id == root.id
    assert child.id != tool.id
    assert child.error == tool.error
    assert child.duration_ms == tool.duration_ms


def test_handler_failure_marks_reexecution_failed(tmp_path):
    rec, trace = _sample(tmp_path)
    registry = HandlerRegistry()

    def fail(_input):
        raise ValueError("lookup failed")

    registry.register("search_kb", fail)
    source = trace.spans[0]
    replay = ReplayController().reexecute(trace, registry, recorder=rec, span_id=source.id)
    assert replay.status == TraceStatus.ERROR
    assert replay.spans[0].error == "lookup failed"
