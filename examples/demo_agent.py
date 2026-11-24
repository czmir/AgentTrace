from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Tuple

from agenttrace.adapters.langgraph import wrap_langgraph_node
from agenttrace.core import SpanKind, TokenUsage, Trace, TraceStatus
from agenttrace.eval import EvalCase
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = os.environ.get("AGENTTRACE_DB", str(ROOT / "data" / "traces.db"))


def _mock_model(session: TraceSession, messages: list[dict], *, tokens: TokenUsage) -> str:
    with session.span("gpt-4o-mini", SpanKind.MODEL, input={"messages": messages}) as span:
        time.sleep(0.02)
        reply = "Acknowledged."
        if messages and "weather" in str(messages[-1].get("content", "")).lower():
            reply = '{"tool": "get_weather", "args": {"city": "Shanghai"}}'
        session.end_span(span, output={"content": reply}, tokens=tokens)
        return reply


def _tool_get_weather(session: TraceSession, city: str, *, fail: bool = False) -> dict:
    with session.span("get_weather", SpanKind.TOOL, input={"city": city}) as span:
        time.sleep(0.01)
        if fail:
            session.end_span(span, error="ConnectionError: weather API unavailable")
            raise RuntimeError("weather API unavailable")
        out = {"city": city, "temp_c": 22, "condition": "clear"}
        session.end_span(span, output=out)
        return out


def _tool_search(session: TraceSession, query: str, *, invalid: bool = False) -> dict:
    attrs = {}
    if invalid:
        attrs["invalid_params"] = "query must be non-empty string"
    with session.span(
        "search_kb", SpanKind.TOOL, input={"query": query}, attributes=attrs
    ) as span:
        if invalid:
            session.end_span(span, error="ValidationError: empty query")
            raise ValueError("empty query")
        session.end_span(span, output={"hits": [{"title": "AgentTrace docs", "score": 0.92}]})
        return {"hits": 1}


@wrap_langgraph_node("plan")
def node_plan(state: dict) -> dict:
    state["plan"] = "answer_user"
    return state


@wrap_langgraph_node("act")
def node_act(state: dict) -> dict:
    state["acted"] = True
    return state


def run_scenario(name: str, recorder: TraceRecorder | None = None) -> Trace:
    rec = recorder or TraceRecorder(DEFAULT_DB)
    with TraceSession(name, recorder=rec, metadata={"scenario": name}) as session:
        with session.span("agent_loop", SpanKind.WORKFLOW) as root:
            messages = [{"role": "user", "content": "What's the weather in Shanghai?"}]

            if name == "context_overflow":
                big = "x" * 500_000
                messages = [{"role": "user", "content": big}]
                tokens = TokenUsage(prompt=140_000, completion=10, total=140_010)
            elif name == "tool_failure":
                tokens = TokenUsage(prompt=120, completion=40, total=160)
            elif name == "human_confirm":
                tokens = TokenUsage(prompt=100, completion=30, total=130)
            else:
                tokens = TokenUsage(prompt=90, completion=25, total=115)

            _mock_model(session, messages, tokens=tokens)
            state = {"messages": messages}
            state = node_plan(state)
            state = node_act(state)

            if name == "human_confirm":
                with session.span("human_approval", SpanKind.HUMAN, input={"action": "send_email"}) as h:
                    session.end_span(h, output={"approved": True})

            if name == "tool_failure":
                try:
                    _tool_get_weather(session, "Shanghai", fail=True)
                except RuntimeError:
                    pass
            elif name == "bad_params":
                try:
                    _tool_search(session, "", invalid=True)
                except ValueError:
                    pass
            else:
                _tool_get_weather(session, "Shanghai")
                if name != "context_overflow":
                    _tool_search(session, "agent tracing")

            if name == "loop_demo":
                for i in range(5):
                    with session.span("retry_tool", SpanKind.TOOL, input={"attempt": i}) as s:
                        session.end_span(s, output={"ok": i == 4})

            root.output = state

        if name in ("tool_failure", "bad_params"):
            session.trace.finish(TraceStatus.ERROR)
    return session.trace


def run_all_scenarios(recorder: TraceRecorder | None = None) -> list[Trace]:
    rec = recorder or TraceRecorder(DEFAULT_DB)
    names = [
        "normal_call",
        "tool_failure",
        "context_overflow",
        "human_confirm",
        "bad_params",
        "loop_demo",
    ]
    return [run_scenario(n, rec) for n in names]


def run_case_for_eval(case: EvalCase, recorder: TraceRecorder) -> Tuple[Any, Trace | None]:
    scenario = case.input.get("scenario", case.id)
    trace = run_scenario(scenario, recorder)
    output = {
        "status": trace.status.value,
        "span_count": len(trace.spans),
        "scenario": scenario,
    }
    for s in trace.spans:
        if case.expected.get("tool_error") and s.kind == SpanKind.TOOL and s.error:
            output["tool_error"] = s.error
    return output, trace


if __name__ == "__main__":
    traces = run_all_scenarios()
    print(f"Recorded {len(traces)} traces to {DEFAULT_DB}")
    for t in traces:
        print(f"  {t.id}  {t.name}  {t.status.value}  spans={len(t.spans)}")