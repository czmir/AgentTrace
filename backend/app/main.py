from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrace.context_analysis import analyze_context
from agenttrace.diagnostics import analyze_trace
from agenttrace.eval import EvalDataset, run_eval_dataset
from agenttrace.recorder import TraceRecorder
from agenttrace.replay import extract_node_inputs, rerun_node
from agenttrace.skills import SkillDefinition, debug_skill_io, run_skill_standalone

DB_PATH = os.environ.get("AGENTTRACE_DB", str(ROOT / "data" / "traces.db"))
recorder = TraceRecorder(DB_PATH)

app = FastAPI(title="AgentTrace API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_event_queue: asyncio.Queue[dict] = asyncio.Queue()


def _on_event(event: str, data: dict) -> None:
    try:
        _event_queue.put_nowait({"event": event, "data": data})
    except Exception:
        pass


recorder.subscribe(_on_event)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": DB_PATH}


@app.get("/api/traces")
def list_traces(limit: int = 50) -> list[dict]:
    return recorder.list_traces(limit)


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    return tr.to_dict()


@app.get("/api/traces/{trace_id}/tree")
def get_trace_tree(trace_id: str) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    return {"trace_id": trace_id, "tree": tr.tree(), "timeline": tr.timeline()}


@app.get("/api/traces/{trace_id}/diagnostics")
def get_diagnostics(trace_id: str) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    findings = [f.to_dict() for f in analyze_trace(tr)]
    return {"trace_id": trace_id, "findings": findings}


@app.get("/api/traces/{trace_id}/context")
def get_context_analysis(trace_id: str) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    return {"trace_id": trace_id, **analyze_context(tr)}


@app.delete("/api/traces/{trace_id}")
def delete_trace(trace_id: str) -> dict:
    if not recorder.delete_trace(trace_id):
        raise HTTPException(404, "trace not found")
    return {"deleted": trace_id}


class ReplayRequest(BaseModel):
    span_id: str


@app.post("/api/traces/{trace_id}/replay")
def replay_node(trace_id: str, body: ReplayRequest) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    node = extract_node_inputs(tr, body.span_id)
    if not node:
        raise HTTPException(404, "span not found")

    def echo_handler(n: dict) -> dict:
        return {"replayed": True, "input": n.get("input")}

    new_trace = rerun_node(tr, body.span_id, echo_handler, recorder=recorder)
    return new_trace.to_dict()


class SkillDebugBody(BaseModel):
    skill_name: str
    input: dict
    output: dict | None = None


@app.post("/api/skills/debug")
def skills_debug(body: SkillDebugBody) -> dict:
    skill_dir = ROOT / "examples" / "skills" / body.skill_name
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise HTTPException(404, "skill not found")
    skill = SkillDefinition.from_markdown_skill(skill_path)
    skill.input_schema = {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string"}},
    }
    if body.output is not None:
        result = debug_skill_io(skill, body.input, body.output)
        return result.model_dump()
    return run_skill_standalone(skill, body.input)


@app.post("/api/eval/run")
def run_eval(body: dict) -> dict:
    path = body.get("dataset_path")
    if not path:
        raise HTTPException(400, "dataset_path required")
    dataset = EvalDataset.load(ROOT / path)
    from examples.demo_agent import run_case_for_eval

    summary = run_eval_dataset(dataset, lambda c: run_case_for_eval(c, recorder), recorder=recorder)
    return summary.model_dump(mode="json")


@app.get("/api/events")
async def sse_events() -> EventSourceResponse:
    async def stream() -> AsyncGenerator[dict, None]:
        while True:
            try:
                item = await asyncio.wait_for(_event_queue.get(), timeout=30.0)
                yield {"event": item["event"], "data": json.dumps(item["data"])}
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(stream())