from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrace import __version__
from agenttrace.context_analysis import analyze_context
from agenttrace.diagnostics import analyze_trace
from agenttrace.eval import EvalConfigError, EvalDataset, run_eval_dataset
from agenttrace.recorder import TraceRecorder
from agenttrace.replay import ReplayController, ReplayMode, extract_node_inputs
from agenttrace.skills import SkillDefinition, debug_skill_io, run_skill_standalone

DB_PATH = os.environ.get("AGENTTRACE_DB", str(ROOT / "data" / "traces.db"))
recorder = TraceRecorder(DB_PATH)
DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="AgentTrace API", version=__version__)

_cors_raw = os.environ.get(
    "AGENTTRACE_CORS",
    "http://127.0.0.1:4321,http://localhost:4321,http://127.0.0.1:8765,http://localhost:8765",
)
_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
    return {"status": "ok", "db": DB_PATH, "version": __version__}


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
    span_id: str | None = None
    mode: str = Field(default=ReplayMode.HISTORY.value)
    allow_side_effects: bool = False
    confirm: bool = False
    bind_version: str | None = None


@app.post("/api/traces/{trace_id}/replay")
def replay_node(trace_id: str, body: ReplayRequest) -> dict:
    tr = recorder.get_trace(trace_id)
    if not tr:
        raise HTTPException(404, "trace not found")
    if body.span_id:
        node = extract_node_inputs(tr, body.span_id)
        if not node:
            raise HTTPException(404, "span not found")

    mode = (body.mode or ReplayMode.HISTORY.value).lower()
    controller = ReplayController()
    if mode == ReplayMode.HISTORY.value:
        new_trace = controller.replay_history(tr, recorder=recorder, span_id=body.span_id)
        return {"mode": mode, "trace": new_trace.to_dict()}
    if mode == ReplayMode.REEXECUTE.value:
        raise HTTPException(
            400,
            "reexecute requires an in-process HandlerRegistry; "
            "HTTP API only supports mode=history (no side effects). "
            "Use ReplayController.reexecute() in your agent process.",
        )
    raise HTTPException(400, f"unknown replay mode {mode!r}; use 'history' or 'reexecute'")


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
    try:
        dataset = EvalDataset.load(ROOT / path)
    except EvalConfigError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError:
        raise HTTPException(404, f"dataset not found: {path}") from None
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


@app.post("/api/demo/order-recovery")
def order_recovery_demo() -> dict:
    try:
        from examples.integrations.langgraph_recovery import run_case
    except ModuleNotFoundError as exc:
        if exc.name != "langgraph":
            raise
        raise HTTPException(503, "Install the integrations extra to run the LangGraph demo") from exc
    return run_case(Path(DB_PATH))


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")


@app.get("/", response_model=None)
def spa_index() -> dict | FileResponse:
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "agenttrace-api", "version": __version__, "ui": "frontend/dist not built"}


@app.get("/{full_path:path}", response_model=None)
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or full_path.split("/", 1)[0] in {
        "health",
        "docs",
        "openapi.json",
        "redoc",
        "assets",
    }:
        raise HTTPException(404, "not found")
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "frontend not built")
