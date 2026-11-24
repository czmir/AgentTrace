# AgentTrace test report (v0.2.0)

Generated from a **real** local run (not edited to hide failures).

## Command

```bash
pip install -e ".[dev,server,integrations]"
cd frontend && npm ci && npm run build
pytest -q --tb=short
python examples/demo_agent.py
python examples/integrations/langgraph_weather.py
python -m agenttrace.cli --version
```

## Results (2026-11-24, this workspace)

| | |
|--|--|
| pytest | **49 passed**, **3 skipped**, 1 warning |
| ruff | All checks passed |
| frontend `npm run build` | ok (vite 5.4.21) |
| Playwright browser E2E | **1 passed** — UI `GET /api/traces` against live FastAPI |
| CLI | `agenttrace 0.2.0` |
| Docker Compose | **not executed here** — `docker` CLI absent on this runner. Files: `docker-compose.yml`, `deploy/nginx.conf` |
| Real LLM | **skipped** — no `OPENAI_API_KEY`. Not faked. |
| Isolated `pip install --target` | **0.2.0** imports from a clean site-packages (`python3-venv` not present on this runner) |

### Skips (honest)

| Test | Reason |
|------|--------|
| `test_real_langgraph_llm_tool_calling` | No `OPENAI_API_KEY` |
| `test_real_openai_sdk` | No `OPENAI_API_KEY` |
| `test_real_mcp_sdk` | `mcp` package not installed / no live MCP server |

### Real integration that did run

- **LangGraph StateGraph** (`test_langgraph_stategraph_real_library` + `examples/integrations/langgraph_weather.py`): compile + invoke, spans `node:lookup` / `get_weather_tool` / `node:format`. Trace `langgraph_stategraph` visible in the UI screenshot.
- Mock demo scenarios remain automated tests (`examples/demo_agent.py`).

## Suites

| Suite | Covers |
|-------|--------|
| `test_sdk.py` | Session tree, decorator, diagnostics |
| `test_session_asyncio.py` | Parallel, nested, exception, task cancel, stale-parent isolation |
| `test_eval.py` / `test_eval_assertions.py` | Golden eval + unknown type / bad config **FAIL** |
| `test_replay.py` | History vs re-execute, version bind, side-effects, human confirm |
| `test_redact.py` | API keys / auth / tool fields |
| `test_adapters.py` | LangGraph wrap, LangChain handler, OpenAI middleware, MCP, async decorator |
| `test_integrations.py` | Real LangGraph; LLM/OpenAI/MCP skip without keys |
| `test_e2e.py` / `test_browser_e2e.py` | FastAPI + Playwright UI |
| `test_cli.py` | list / show / diagnose / replay / eval |
| `test_frontend_wiring.py` | Vite + nginx proxy to real API |
