"""Run a reproducible LangGraph failure, tool repair, and regression check."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agenttrace.adapters.langgraph import wrap_langgraph_node
from agenttrace.core import SpanKind
from agenttrace.diagnostics import analyze_trace
from agenttrace.eval import (
    EvalAssertion,
    EvalCase,
    EvalDataset,
    compare_eval_runs,
    run_eval_dataset,
)
from agenttrace.recorder import TraceRecorder
from agenttrace.replay import HandlerRegistry, ReplayController
from agenttrace.session import TraceSession, get_current_session


class OrderState(TypedDict, total=False):
    order_id: str
    status: str


ORDERS = {"A-104": "shipped", "B-201": "processing"}


def lookup_order(order_id: str, *, fixed: bool) -> dict[str, str]:
    key = order_id.strip().upper() if fixed else order_id
    if key not in ORDERS:
        raise LookupError(f"Order {key!r} was not found")
    return {"status": ORDERS[key]}


def run_case(db_path: Path) -> dict:
    recorder = TraceRecorder(db_path)
    dataset = EvalDataset(
        name="order-id-normalization",
        cases=[
            EvalCase(
                id="mixed-case-and-whitespace",
                input={"order_id": " a-104 "},
                assertions=[EvalAssertion(type="path_eq", path="status", expected="shipped")],
            ),
            EvalCase(
                id="canonical-id",
                input={"order_id": "B-201"},
                assertions=[EvalAssertion(type="path_eq", path="status", expected="processing")],
            ),
        ],
    )

    def evaluate(fixed: bool):
        @wrap_langgraph_node("resolve_order")
        async def resolve_order(state: OrderState) -> OrderState:
            session = get_current_session()
            async with session.aspan("lookup_order", SpanKind.TOOL, input=state) as span:
                result = lookup_order(state["order_id"], fixed=fixed)
                span.output = result
                return result

        graph = StateGraph(OrderState)
        graph.add_node("resolve_order", resolve_order)
        graph.add_edge(START, "resolve_order")
        graph.add_edge("resolve_order", END)
        agent = graph.compile()

        async def execute(case: EvalCase):
            version = "normalized" if fixed else "baseline"
            session = TraceSession(
                f"orders/{version}/{case.id}", recorder=recorder, metadata={"version": version},
            )
            try:
                async with session, session.aspan("agent", SpanKind.WORKFLOW):
                    output = await agent.ainvoke(case.input)
            except LookupError as exc:
                output = {"error": str(exc)}
            return output, session.trace

        return run_eval_dataset(dataset, lambda case: asyncio.run(execute(case)), recorder=recorder)

    baseline = evaluate(False)
    failed = recorder.get_trace(baseline.results[0].trace_id)
    source = next(span for span in failed.spans if span.kind == SpanKind.TOOL and span.error)
    registry = HandlerRegistry()
    registry.register("lookup_order", lambda payload: lookup_order(payload["order_id"], fixed=True))
    controller = ReplayController()
    history = controller.replay_history(failed, recorder=recorder)
    retry = controller.reexecute(failed, registry, recorder=recorder, span_id=source.id)
    candidate = evaluate(True)
    return {
        "failed_trace": failed.id,
        "failed_span": source.id,
        "diagnostics": [finding.to_dict() for finding in analyze_trace(failed)],
        "history_trace": history.id,
        "retry_trace": retry.id,
        "retry_status": retry.status.value,
        "retry_output": retry.spans[0].output,
        "baseline": baseline.model_dump(mode="json"),
        "candidate": candidate.model_dump(mode="json"),
        "comparison": compare_eval_runs(baseline, candidate),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/traces.db"))
    args = parser.parse_args()
    report = run_case(args.db)
    print(json.dumps(report, indent=2))
    raise SystemExit(report["candidate"]["failed"] or report["retry_status"] != "ok")
