#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,server,integrations]"
pip install -r backend/requirements.txt

export AGENTTRACE_DB="$ROOT/data/traces.db"
mkdir -p data
python examples/demo_agent.py

echo "Starting API on :8765 and UI on :4321"
uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 &
API_PID=$!
cd frontend && npm ci && npm run dev &
UI_PID=$!
trap "kill $API_PID $UI_PID 2>/dev/null" EXIT
wait
