# Limitations (honest)

This is **implemented vs test-only vs known limits**. Docs do not paper over missing vendor credentials.

## Implemented

- SQLite recorder, sync + async `TraceSession`, contextvar parent/child spans
- Decorators and adapters for LangGraph nodes, LangChain-style callbacks, OpenAI-compatible chat, MCP wrappers
- History replay (copy stored I/O) vs in-process re-execute (`HandlerRegistry`, version bind, side-effect limits, human confirm)
- Eval assertions: unknown types / missing fields / invalid ops **fail the case**
- Redaction of API keys, auth headers, and secret-like fields in persisted traces
- FastAPI + React UI; Vite and Docker nginx proxy `/api` to the real backend
- Mock demo scenarios (`examples/demo_agent.py`) as automated tests

## Test-only / optional

- **Real LLM E2E** (`tests/test_integrations.py::test_real_langgraph_llm_tool_calling`) runs only when `OPENAI_API_KEY` (or `OPENAI_API_KEY` + `OPENAI_BASE_URL`) is set. CI without a key **skips** this test. It does **not** invent token usage or model text.
- Real LangChain `ChatOpenAI` / OpenAI SDK / MCP Python SDK tests skip when the extra or key is absent. Adapter unit tests use fakes and are labeled as such.
- Playwright browser E2E skips if Chromium/Chrome cannot launch.

## Known limits

- HTTP `/api/traces/{id}/replay` only supports `mode=history`. Real re-execute needs an in-process `HandlerRegistry` (side effects must not be triggered from the UI).
- No hosted SaaS, no multi-tenant auth. Local-first.
- OTLP exporter helper maps spans to dicts; it does not ship a collector.
- Redaction is pattern + field-name based. It cannot guarantee every secret shape.
- Windows Docker needs Docker Desktop; `scripts/quickstart.ps1` needs Python and Node on PATH.
