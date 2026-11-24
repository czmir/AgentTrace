# AgentTrace test report

Generated during CI / local `pytest`.

## Scope

| Suite | What it covers |
|-------|----------------|
| `tests/test_sdk.py` | Session, decorator, SQLite recorder, diagnostics |
| `tests/test_eval.py` | Golden dataset run + regression diff |
| `tests/test_e2e.py` | Demo agent subprocess + FastAPI routes |

## E2E scenarios (via `examples/demo_agent.py`)

- **normal_call** — happy path model + tools
- **tool_failure** — tool error surfaced in trace + diagnostics
- **context_overflow** — high prompt token usage flagged
- **human_confirm** — human approval span
- **bad_params** — invalid tool params
- **loop_demo** — repeated spans → loop diagnostic

## How to run

```bash
pip install -e ".[dev,server]"
pytest -q
```