"""Vendor integrations: real LangGraph when installed; real LLM only with an API key.

Never fake model tokens or completions.
"""

from __future__ import annotations

import os

import pytest

from agenttrace.recorder import TraceRecorder

LLM_SKIP = (
    "No OPENAI_API_KEY; real LangGraph+LLM+tool-calling E2E skipped "
    "(not faked). See docs/LIMITATIONS.md"
)


def test_langgraph_stategraph_real_library(tmp_path):
    pytest.importorskip("langgraph")
    from examples.integrations.langgraph_weather import run_langgraph_stategraph

    rec = TraceRecorder(tmp_path / "t.db")
    tr = run_langgraph_stategraph(rec)
    names = [s.name for s in tr.spans]
    assert any(n.startswith("node:lookup") for n in names)
    assert any(n.startswith("node:format") for n in names)
    assert tr.metadata.get("result", {}).get("answer")


@pytest.mark.integration
def test_real_langgraph_llm_tool_calling(tmp_path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip(LLM_SKIP)
    pytest.importorskip("langgraph")
    pytest.importorskip("langchain_openai")
    from examples.integrations.langgraph_weather import run_langgraph_llm_tools

    rec = TraceRecorder(tmp_path / "t.db")
    tr = run_langgraph_llm_tools(rec)
    assert tr.spans, "expected real spans from LangGraph + LLM"
    model_spans = [s for s in tr.spans if s.kind.value == "model"]
    assert model_spans, "expected a real model span (not mocked)"
    assert any(s.tokens.total > 0 or s.output for s in model_spans)


@pytest.mark.integration
def test_real_openai_sdk(tmp_path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("No OPENAI_API_KEY; real OpenAI SDK call skipped (not faked).")
    openai = pytest.importorskip("openai")
    from agenttrace.adapters.openai_compat import OpenAITraceMiddleware
    from agenttrace.core import SpanKind
    from agenttrace.session import TraceSession

    rec = TraceRecorder(tmp_path / "t.db")
    client = openai.OpenAI()
    mw = OpenAITraceMiddleware(client)
    with TraceSession("openai_real", recorder=rec):
        resp = mw.chat_completions_create(
            model=os.environ.get("AGENTTRACE_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Reply with the single word pong."}],
        )
    text = resp.choices[0].message.content or ""
    assert text.strip()
    tr = rec.get_trace(rec.list_traces()[0]["id"])
    span = next(s for s in tr.spans if s.kind == SpanKind.MODEL)
    assert span.tokens.total > 0


@pytest.mark.integration
def test_real_mcp_sdk():
    pytest.importorskip("mcp")
    pytest.skip(
        "mcp package present but no live MCP server configured; "
        "decorator coverage is in tests/test_adapters.py (not faked as a server)."
    )


def test_langchain_example_fake_callbacks(tmp_path, monkeypatch):
    """The shipped langchain_example is a callback sketch, not a real LLM run."""
    from examples.integrations.langchain_example import demo

    monkeypatch.chdir(tmp_path)
    demo()
