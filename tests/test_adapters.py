import inspect
from uuid import uuid4

import pytest

from agenttrace.adapters.langchain_callback import AgentTraceHandler
from agenttrace.adapters.langgraph import wrap_langgraph_node
from agenttrace.adapters.mcp import trace_mcp_tool_call
from agenttrace.adapters.openai_compat import OpenAITraceMiddleware
from agenttrace.core import SpanKind, TokenUsage
from agenttrace.decorators import trace_span
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession


def test_langgraph_wrap_sync(tmp_path):
    @wrap_langgraph_node("plan")
    def plan(state: dict) -> dict:
        return {**state, "plan": True}

    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("lg", recorder=rec):
        out = plan({"q": 1})
    assert out["plan"] is True
    tr = rec.list_traces()
    t = rec.get_trace(tr[0]["id"])
    assert any(s.name == "node:plan" for s in t.spans)


@pytest.mark.asyncio
async def test_async_decorator(tmp_path):
    @trace_span("async_tool", kind=SpanKind.TOOL)
    async def work(x: int) -> int:
        return x + 1

    rec = TraceRecorder(tmp_path / "t.db")
    async with TraceSession("ad", recorder=rec):
        assert await work(2) == 3
    t = rec.get_trace(rec.list_traces()[0]["id"])
    assert t.spans[0].name == "async_tool"
    assert t.spans[0].output == 3


def test_openai_middleware_fake_client(tmp_path):
    class Usage:
        prompt_tokens = 11
        completion_tokens = 5
        total_tokens = 16

    class Msg:
        content = "hello"
        tool_calls = None

    class Choice:
        message = Msg()

    class Resp:
        def __init__(self) -> None:
            self.usage = Usage()
            self.choices = [Choice()]

    class Completions:
        def create(self, **kwargs):
            return Resp()

    class Chat:
        completions = Completions()

    class Client:
        chat = Chat()

    rec = TraceRecorder(tmp_path / "t.db")
    mw = OpenAITraceMiddleware(Client())
    with TraceSession("oa", recorder=rec):
        resp = mw.chat_completions_create(model="gpt-test", messages=[{"role": "user", "content": "hi"}])
    assert resp.choices[0].message.content == "hello"
    t = rec.get_trace(rec.list_traces()[0]["id"])
    span = t.spans[0]
    assert span.kind == SpanKind.MODEL
    assert span.tokens == TokenUsage(prompt=11, completion=5, total=16)


def test_langchain_handler_parent_child(tmp_path):
    h = AgentTraceHandler()
    rec = TraceRecorder(tmp_path / "t.db")
    chain_id, llm_id = uuid4(), uuid4()
    with TraceSession("lc", recorder=rec):
        h.on_chain_start({"name": "Research"}, {"q": "x"}, run_id=chain_id)
        h.on_llm_start({"name": "Chat"}, ["hello"], run_id=llm_id, parent_run_id=chain_id)
        h.on_llm_end("out", run_id=llm_id, parent_run_id=chain_id)
        h.on_chain_end({"a": 1}, run_id=chain_id)
    t = rec.get_trace(rec.list_traces()[0]["id"])
    chain = next(s for s in t.spans if s.name == "Research")
    llm = next(s for s in t.spans if s.name == "Chat")
    assert llm.parent_id == chain.id


def test_mcp_wrapper(tmp_path):
    @trace_mcp_tool_call("weather", "get")
    def get(city: str) -> dict:
        return {"city": city}

    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("mcp", recorder=rec):
        assert get("Shanghai")["city"] == "Shanghai"
    t = rec.get_trace(rec.list_traces()[0]["id"])
    assert t.spans[0].kind.value == "mcp"
    assert t.spans[0].attributes["mcp_server"] == "weather"


def test_async_openai_method_exists():
    assert inspect.iscoroutinefunction(OpenAITraceMiddleware.achat_completions_create)
