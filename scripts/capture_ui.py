#!/usr/bin/env python3
"""Seed traces, serve API+UI, capture screenshots + a short GIF from a real browser."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
SHOTS = ROOT / "docs" / "screenshots"


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    if not (DIST / "index.html").is_file():
        subprocess.check_call(["npm", "ci"], cwd=ROOT / "frontend")
        subprocess.check_call(["npm", "run", "build"], cwd=ROOT / "frontend")
    SHOTS.mkdir(parents=True, exist_ok=True)
    db = ROOT / "data" / "traces.db"
    db.parent.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["AGENTTRACE_DB"] = str(db)
    subprocess.check_call([sys.executable, str(ROOT / "examples" / "demo_agent.py")], cwd=ROOT, env=env)
    try:
        subprocess.check_call(
            [sys.executable, str(ROOT / "examples" / "integrations" / "langgraph_weather.py")],
            cwd=ROOT,
            env=env,
        )
    except Exception as e:
        print("langgraph example skipped/failed (honest):", e)

    port = _port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit("API did not start")

        from playwright.sync_api import sync_playwright

        chrome = Path("/usr/local/bin/google-chrome")
        kwargs: dict = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chrome.exists():
            kwargs["executable_path"] = str(chrome)
        with sync_playwright() as p:
            browser = p.chromium.launch(**kwargs)
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.goto(url + "/", wait_until="networkidle")
            page.screenshot(path=str(SHOTS / "trace-list.png"))
            page.locator("a", has_text="Open").first.click()
            page.wait_for_timeout(800)
            page.screenshot(path=str(SHOTS / "trace-detail.png"))
            page.goto(url + "/eval", wait_until="networkidle")
            page.locator("button", has_text="Run golden v1").click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(SHOTS / "eval.png"))
            frames = []
            page.goto(url + "/", wait_until="networkidle")
            frames.append(page.screenshot())
            page.locator("a", has_text="Open").first.click()
            page.wait_for_timeout(600)
            frames.append(page.screenshot())
            page.locator("button", has_text="History replay").click()
            page.wait_for_timeout(800)
            frames.append(page.screenshot())
            page.goto(url + "/eval", wait_until="networkidle")
            frames.append(page.screenshot())
            browser.close()

        gif_dir = SHOTS / "_frames"
        gif_dir.mkdir(exist_ok=True)
        for i, png in enumerate(frames):
            (gif_dir / f"f{i}.png").write_bytes(png)
        gif = SHOTS / "demo-agenttrace.gif"
        subprocess.check_call(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                "1",
                "-i",
                str(gif_dir / "f%d.png"),
                "-vf",
                "scale=960:-1:flags=lanczos",
                str(gif),
            ]
        )
        for f in gif_dir.glob("*.png"):
            f.unlink()
        gif_dir.rmdir()
        print("wrote", SHOTS)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
