# Windows 启动 / Windows start

AgentTrace 在 Windows 10/11 + Python 3.11+ + Node 20 上可用。PowerShell 执行策略若拦截脚本，先运行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Quick start

```powershell
git clone https://github.com/czmir/AgentTrace.git
cd AgentTrace
.\scripts\quickstart.ps1
```

或 CMD：`scripts\quickstart.cmd`

手动步骤：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,server]"
$env:AGENTTRACE_DB = "$PWD\data\traces.db"
New-Item -ItemType Directory -Force data
python examples\demo_agent.py
uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
# 新终端
cd frontend
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:4321`。Vite 会把 `/api` **proxy** 到 FastAPI `:8765`。

## Docker Desktop

```powershell
docker compose up --build
```

UI `:4321` → nginx reverse-proxy → API `:8765`（same-origin `/api`，不是 mock）。

## CLI

```powershell
agenttrace --version
agenttrace --db .\data\traces.db list
```
