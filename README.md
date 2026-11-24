# AgentTrace

**Lightweight agent execution tracing, debugging, and eval** for LLM / Agent / Agent Skill developers.

AgentTrace is **local-first**, **independently installable**, and **not** a full agent platform. Plug the Python SDK into existing apps, inspect runs in a small React UI, and gate releases with golden evals.

[中文文档](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Limitations](docs/LIMITATIONS.md) · [Windows](docs/windows.md) · [Test report](tests/TEST_REPORT.md) · [Security](SECURITY.md)

![AgentTrace UI — trace list](docs/screenshots/trace-list.png)

![Trace detail — tree, timeline, diagnostics](docs/screenshots/trace-detail.png)

![Demo GIF](docs/screenshots/demo-agenttrace.gif)

## Why AgentTrace?

| Problem | AgentTrace |
|---------|------------|
| Opaque agent execution | Tree + timeline spans (model / tool / workflow / human / MCP) |
| Hard-to-debug tool calls | Per-span I/O, diagnostics (failures, loops, bad params, context) |
| Hard-to-reproduce failures | SQLite history + **history replay** (copy I/O) vs **re-execute** (handler registry) |
| No regression evals | Golden datasets, assertions (unknown types **fail**, they do not pass) |

**Compared to Langfuse / Phoenix / LangSmith:** smaller deploy surface (SQLite default), explicit **skill I/O debug**, and **low integration cost** — decorators + optional adapters, not a hosted platform.

## Quick start

```bash
git clone https://github.com/czmir/AgentTrace.git
cd AgentTrace
./scripts/quickstart.sh
```

Windows: [`docs/windows.md`](docs/windows.md) / `scripts\quickstart.ps1`.

Or manually:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,server]"
export AGENTTRACE_DB=./data/traces.db
python examples/demo_agent.py
uvicorn backend.app.main:app --port 8765 &
cd frontend && npm install && npm run dev
```

Open the UI at `http://127.0.0.1:4321`. Vite **proxies `/api` to FastAPI :8765** (real backend, not a mock). After `npm run build`, FastAPI also serves `frontend/dist` on `:8765`.

## Python SDK

```python
from agenttrace import TraceSession, trace_span
from agenttrace.core import SpanKind
from agenttrace.recorder import TraceRecorder

rec = TraceRecorder("./data/traces.db")

with TraceSession("my-agent", recorder=rec) as session:
    with session.span("plan", SpanKind.WORKFLOW) as span:
        span.output = {"step": "search"}
```

Async:

```python
async with TraceSession("async-agent", recorder=rec) as session:
    async with session.aspan("tool", SpanKind.TOOL):
        ...
```

- **Decorators:** `@trace_span("tool_name", kind=SpanKind.TOOL)` (sync + async)
- **Adapters:** `agenttrace.adapters` (LangGraph node wrapper, LangChain-style handler, OpenAI middleware, MCP wrapper)
- **CLI:** `agenttrace list`, `agenttrace diagnose <id>`, `agenttrace replay <id>`, `agenttrace eval examples/eval/golden_v1.json --example`

## Features (v0.2.0)

1. SDK — sessions, asyncio-safe parent/child spans, SQLite recorder, redaction, OTel mapping helper
2. UI — trace list, tree, timeline, diagnostics, context panel, eval trigger, history replay
3. Skill debug — load `SKILL.md`, JSON Schema validation, param checks
4. Replay — `ReplayController.replay_history` vs `reexecute` (handler registry, version bind, side-effect limits, human confirm). HTTP API is **history-only**
5. Eval — golden cases; unknown assertion types / invalid fields **fail clearly**
6. Data safety — API keys, `Authorization`, secret-like fields redacted in persisted traces

## E2E demo scenarios (mock — automated tests)

`examples/demo_agent.py` records **deterministic mock** runs (not a live LLM):

- `normal_call` · `tool_failure` · `context_overflow` · `human_confirm` · `bad_params` · `loop_demo`

Real LangGraph `StateGraph` (+ optional real LLM tool calling) lives in `examples/integrations/langgraph_weather.py`. Without `OPENAI_API_KEY` the LLM test is **skipped**, not faked. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Docker Compose

```bash
docker compose up --build
```

UI `:4321` (nginx) reverse-proxies `/api` to the API container. Frontend always hits the real backend.

## License

MIT — see [LICENSE](LICENSE).
