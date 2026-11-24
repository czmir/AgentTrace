@echo off
setlocal
cd /d "%~dp0\.."
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required. See docs\windows.md
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -U pip
pip install -e ".[dev,server]"
pip install -r backend\requirements.txt
if not exist data mkdir data
set AGENTTRACE_DB=%CD%\data\traces.db
python examples\demo_agent.py
echo Starting API on :8765
start "agenttrace-api" cmd /c uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
cd frontend
if not exist node_modules npm install
echo Open http://127.0.0.1:4321
npm run dev
