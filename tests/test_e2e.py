import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "e2e.db"


def test_demo_agent_produces_traces(db_path, monkeypatch):
    monkeypatch.setenv("AGENTTRACE_DB", str(db_path))
    subprocess.check_call([sys.executable, str(ROOT / "examples" / "demo_agent.py")], cwd=ROOT)
    assert db_path.exists()


@pytest.mark.asyncio
async def test_api_list_traces(db_path, monkeypatch):
    monkeypatch.setenv("AGENTTRACE_DB", str(db_path))
    subprocess.check_call([sys.executable, str(ROOT / "examples" / "demo_agent.py")], cwd=ROOT)

    monkeypatch.setenv("AGENTTRACE_DB", str(db_path))
    import importlib

    import backend.app.main as main_mod

    importlib.reload(main_mod)
    app = main_mod.app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/traces")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 6
        tid = data[0]["id"]
        tree = await client.get(f"/api/traces/{tid}/tree")
        assert tree.status_code == 200
        assert "timeline" in tree.json()
        diag = await client.get(f"/api/traces/{tid}/diagnostics")
        assert diag.status_code == 200
        replay = await client.post(
            f"/api/traces/{tid}/replay", json={"mode": "history"}
        )
        assert replay.status_code == 200
        assert replay.json()["mode"] == "history"
        blocked = await client.post(
            f"/api/traces/{tid}/replay", json={"mode": "reexecute"}
        )
        assert blocked.status_code == 400
        bad_eval = await client.post("/api/eval/run", json={"dataset_path": "missing.json"})
        assert bad_eval.status_code in (400, 404)