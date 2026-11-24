#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export AGENTTRACE_DB="$ROOT/data/traces.db"
mkdir -p data
python examples/demo_agent.py