"""Real LangGraph StateGraph (+ optional real LLM tool calling).

Graph-only path uses LangGraph with Python nodes — no fake LLM traces.
LLM path requires OPENAI_API_KEY and is skipped when the key is absent.
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

from agenttrace.adapters.langgraph import wrap_langgraph_node
from agenttrace.core import SpanKind, Trace
from agenttrace.decorators import trace_span
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession

LLM_SKIP_REASON = (
    "No OPENAI_API_KEY; real LangGraph+LLM+tool-calling E2E skipped "
    "(not faked). See docs/LIMITATIONS.md"
)


class WeatherState(TypedDict, total=False):
    city: str
    weather: str
    answer: str


@wrap_langgraph_node("lookup")
@trace_span("get_weather_tool", kind=SpanKind.TOOL)
def lookup_weather(state: WeatherState) -> WeatherState:
    city = state.get("city") or "Shanghai"
    return {**state, "weather": f"{city}: 22C clear (deterministic tool)"}


@wrap_langgraph_node("format")
def format_answer(state: WeatherState) -> WeatherState:
    return {**state, "answer": f"Weather report: {state.get('weather')}"}


def build_state_graph():
    from langgraph.graph import END, StateGraph

    g: Any = StateGraph(WeatherState)
    g.add_node("lookup", lookup_weather)
    g.add_node("format", format_answer)
    g.set_entry_point("lookup")
    g.add_edge("lookup", "format")
    g.add_edge("format", END)
    return g.compile()


def run_langgraph_stategraph(recorder: TraceRecorder | None = None) -> Trace:
    """Real LangGraph compile+invoke, no LLM."""
    rec = recorder or TraceRecorder()
    graph = build_state_graph()
    with TraceSession("langgraph_stategraph", recorder=rec, metadata={"kind": "langgraph"}) as session:
        result = graph.invoke({"city": "Shanghai"})
        session.trace.metadata["result"] = result
    return session.trace


def llm_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def run_langgraph_llm_tools(recorder: TraceRecorder | None = None) -> Trace:
    """Real model + tool calling via LangGraph prebuilt ReAct agent. Raises if no key."""
    if not llm_available():
        raise RuntimeError(LLM_SKIP_REASON)

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    rec = recorder or TraceRecorder()

    @tool
    def get_weather(city: str) -> str:
        """Return weather for a city (deterministic tool, real LLM decides to call it)."""
        return f"{city}: 22C, clear"

    model_name = os.environ.get("AGENTTRACE_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0)
    agent = create_react_agent(llm, [get_weather])

    from agenttrace.adapters.langchain_callback import AgentTraceHandler

    handler = AgentTraceHandler()
    with TraceSession(
        "langgraph_llm_tools",
        recorder=rec,
        metadata={"kind": "langgraph_llm", "model": model_name},
    ) as session:
        result = agent.invoke(
            {"messages": [("user", "What is the weather in Shanghai? Use the tool.")]},
            config={"callbacks": [handler]},
        )
        session.trace.metadata["messages"] = str(result.get("messages", []))[-500:]
    return session.trace


if __name__ == "__main__":
    from pathlib import Path

    rec = TraceRecorder(Path("./data/traces.db"))
    tr = run_langgraph_stategraph(rec)
    print("stategraph", tr.id, "spans", len(tr.spans))
    if llm_available():
        tr2 = run_langgraph_llm_tools(rec)
        print("llm", tr2.id, "spans", len(tr2.spans), "tokens", sum(s.tokens.total for s in tr2.spans))
    else:
        print("SKIP llm:", LLM_SKIP_REASON)
