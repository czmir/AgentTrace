import asyncio

import pytest

from agenttrace.core import SpanKind, TraceStatus
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession


@pytest.mark.asyncio
async def test_parallel_spans_keep_parent_child(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    async with TraceSession("par", recorder=rec) as session:

        async def job(n: int) -> None:
            async with session.aspan(f"p{n}", SpanKind.WORKFLOW):
                await asyncio.sleep(0.02)
                async with session.aspan(f"c{n}", SpanKind.TOOL):
                    await asyncio.sleep(0.02)

        await asyncio.gather(job(1), job(2), job(3))

    tr = rec.get_trace(session.trace.id)
    assert tr is not None
    by_name = {s.name: s for s in tr.spans}
    assert by_name["c1"].parent_id == by_name["p1"].id
    assert by_name["c2"].parent_id == by_name["p2"].id
    assert by_name["c3"].parent_id == by_name["p3"].id
    assert by_name["p1"].parent_id is None
    assert by_name["p2"].parent_id is None
    assert by_name["p3"].parent_id is None
    assert len(tr.tree()) == 3


def test_new_session_does_not_inherit_stale_parent(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("first", recorder=rec) as s1:
        s1.start_span("orphan", SpanKind.WORKFLOW)
        # deliberately do not end_span — close must not leak parent into next session
    with TraceSession("second", recorder=rec) as s2:
        with s2.span("root", SpanKind.WORKFLOW):
            pass
    tr = rec.get_trace(s2.trace.id)
    assert tr is not None
    assert tr.spans[0].parent_id is None
    assert len(tr.tree()) == 1


@pytest.mark.asyncio
async def test_nested_spans(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    async with TraceSession("nest", recorder=rec) as session:
        async with session.aspan("a", SpanKind.WORKFLOW):
            async with session.aspan("b", SpanKind.WORKFLOW):
                async with session.aspan("c", SpanKind.TOOL):
                    pass
    tr = rec.get_trace(session.trace.id)
    by_name = {s.name: s for s in tr.spans}
    assert by_name["a"].parent_id is None
    assert by_name["b"].parent_id == by_name["a"].id
    assert by_name["c"].parent_id == by_name["b"].id
    tree = tr.tree()
    assert tree[0]["span"]["name"] == "a"
    assert tree[0]["children"][0]["span"]["name"] == "b"
    assert tree[0]["children"][0]["children"][0]["span"]["name"] == "c"


@pytest.mark.asyncio
async def test_exception_exit_marks_error(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with pytest.raises(RuntimeError, match="boom"):
        async with TraceSession("ex", recorder=rec) as session:
            async with session.aspan("boom", SpanKind.TOOL):
                raise RuntimeError("boom")
    tr = rec.get_trace(session.trace.id)
    assert tr is not None
    assert tr.status == TraceStatus.ERROR
    span = tr.spans[0]
    assert span.error == "boom"
    assert span.end_ns is not None


@pytest.mark.asyncio
async def test_task_cancel_ends_span(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    async with TraceSession("cancel", recorder=rec) as session:

        async def long_job() -> None:
            async with session.aspan("long", SpanKind.WORKFLOW):
                await asyncio.sleep(30)

        task = asyncio.create_task(long_job())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    tr = rec.get_trace(session.trace.id)
    assert tr is not None
    assert tr.status == TraceStatus.OK
    long = next(s for s in tr.spans if s.name == "long")
    assert long.end_ns is not None
    assert long.error == "cancelled"


@pytest.mark.asyncio
async def test_session_cancel_status(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")

    async def outer() -> None:
        async with TraceSession("outer", recorder=rec) as session:
            async with session.aspan("inner"):
                await asyncio.sleep(30)
            _ = session

    task = asyncio.create_task(outer())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    traces = rec.list_traces()
    assert traces
    tr = rec.get_trace(traces[0]["id"])
    assert tr is not None
    assert tr.status == TraceStatus.CANCELLED
