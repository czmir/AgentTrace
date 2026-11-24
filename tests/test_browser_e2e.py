"""Playwright E2E: UI must hit the real FastAPI backend (no mocked fetch)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server():
    if not (DIST / "index.html").is_file():
        pytest.skip("frontend/dist not built; run `cd frontend && npm ci && npm run build`")
    chrome = os.environ.get("PLAYWRIGHT_CHROME", "/usr/local/bin/google-chrome")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    db = ROOT / "data" / "e2e-browser.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENTTRACE_DB"] = str(db)
    subprocess.check_call([sys.executable, str(ROOT / "examples" / "demo_agent.py")], cwd=ROOT, env=env)

    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    import urllib.error
    import urllib.request

    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
            pytest.fail(f"uvicorn exited early: {out}")
        try:
            urllib.request.urlopen(f"{url}/health", timeout=1)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("API did not become healthy")

    yield {"url": url, "chrome": chrome, "playwright": sync_playwright}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.browser
def test_ui_lists_traces_from_real_api(live_server, tmp_path):
    sync_playwright = live_server["playwright"]
    url = live_server["url"]
    chrome = live_server["chrome"]
    launch_kwargs = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if Path(chrome).exists():
        launch_kwargs["executable_path"] = chrome

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as e:
            pytest.skip(f"Chromium/Chrome could not launch: {e}")
        page = browser.new_page()
        api_hits: list[int] = []

        def on_response(resp):
            if "/api/traces" in resp.url and resp.request.method == "GET":
                api_hits.append(resp.status)

        page.on("response", on_response)
        page.goto(url + "/", wait_until="networkidle", timeout=30_000)
        body = page.inner_text("body")
        assert "AgentTrace" in body
        assert api_hits, "UI did not call GET /api/traces on the real backend"
        assert 200 in api_hits
        assert "normal_call" in body or "Open" in body
        page.screenshot(path=str(tmp_path / "trace-list.png"))
        if page.locator("a", has_text="Open").count():
            page.locator("a", has_text="Open").first.click()
            page.wait_for_timeout(500)
            detail = page.inner_text("body")
            assert "Span tree" in detail or "Timeline" in detail
            page.screenshot(path=str(tmp_path / "trace-detail.png"))
        page.goto(url + "/eval", wait_until="networkidle")
        page.locator("button", has_text="Run golden v1").click()
        page.wait_for_timeout(2000)
        eval_body = page.inner_text("body")
        assert "passed" in eval_body.lower() or "failed" in eval_body.lower() or "{" in eval_body
        page.screenshot(path=str(tmp_path / "eval.png"))
        browser.close()

