"""Capture the order recovery walkthrough from a running AgentTrace instance."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def capture(url: str, output: Path, browser_channel: str | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=browser_channel)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{url.rstrip('/')}/eval")
        page.get_by_role("button", name="Run LangGraph recovery").click()
        results = page.get_by_role("region", name="Order recovery results")
        expect(results).to_contain_text("Baseline 1/2 · Candidate 2/2", timeout=30_000)
        page.screenshot(path=output / "recovery-eval.png")
        page.get_by_role("link", name="Inspect the failed run").click()
        expect(page.get_by_role("heading", name="Diagnostics")).to_be_visible()
        expect(page.get_by_text("[tool_failure]", exact=False)).to_be_visible()
        page.screenshot(path=output / "recovery-failure.png")
        page.get_by_role("button", name="History replay").click()
        expect(page.get_by_role("heading", name="history_replay:", exact=False)).to_be_visible()
        expect(page.get_by_text("[tool_failure]", exact=False)).to_be_visible()
        page.screenshot(path=output / "recovery-history.png")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots"))
    parser.add_argument("--browser-channel", help="Use an installed channel such as msedge")
    args = parser.parse_args()
    capture(args.url, args.output, args.browser_channel)
