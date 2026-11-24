# AgentTrace Windows quickstart (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.11+ is required. Install from https://www.python.org/downloads/windows/"
}

python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev,server]"
pip install -r backend/requirements.txt

New-Item -ItemType Directory -Force -Path data | Out-Null
$env:AGENTTRACE_DB = Join-Path (Get-Location) "data\traces.db"
python examples/demo_agent.py

Write-Host "Starting API on :8765 and UI on :4321"
Start-Process -NoNewWindow -FilePath "uvicorn" -ArgumentList "backend.app.main:app","--host","127.0.0.1","--port","8765"
Set-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run dev
