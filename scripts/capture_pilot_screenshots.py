"""Capture before/after screenshots for the PR-CHART-2 pilot pages.

Boots a Playwright browser against an already-running streamlit
dashboard (http://localhost:8506) and screenshots:

    - Alert Queue (rule severity bar + severity donut + alert table + case table)
    - Live Monitor (idle state — full live-update render needs the
      "Start Monitoring" button so we capture the screening-rules
      expander + ready state instead)

Outputs to docs/screenshots/chart-migration/. Throwaway script —
not wired into the test suite — so the conventions are loose.
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots" / "chart-migration"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Tall viewport so the chart row + tables both end up in one
        # screenshot without relying on full_page=True (which doesn't
        # always expand correctly when the page uses position:sticky
        # chrome like Streamlit's topbar).
        ctx = browser.new_context(viewport={"width": 1600, "height": 2400})
        page = ctx.new_page()

        # Alert Queue — pages/3_Alert_Queue
        # Streamlit's URL-routing for multi-page apps is /3_Alert_Queue
        # (file index + display name).
        # Streamlit's multi-page URL slug is the file's display name
        # (drop the numeric prefix, keep the underscores). E.g.
        # `pages/3_Alert_Queue.py` → `/Alert_Queue`.

        # Alert Queue — static page; just navigate + wait + screenshot.
        page.goto("http://localhost:8506/Alert_Queue", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(4000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(800)
        target = OUT / "alert_queue_after.png"
        page.screenshot(path=str(target), full_page=True)
        print(f"   saved {target} ({target.stat().st_size // 1024}KB)", file=sys.stderr)

        # Live Monitor — click Start Monitoring + wait for the live
        # charts to populate, then screenshot MID-STREAM. Don't click
        # Stop — that triggers a Streamlit rerun which clears the
        # placeholder-rendered charts back to the idle state.
        # Speed defaults to "Fast" (0.1s/tick × every 3 = ~0.3s/render);
        # 8 seconds is plenty for both charts to acquire meaningful
        # cumulative-volume + channel-distribution data.
        page.goto("http://localhost:8506/Live_Monitor", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="Start Monitoring").click()
        page.wait_for_timeout(10000)  # let the live loop populate charts
        # Don't scroll — the charts are above the fold and scrolling
        # might trigger the live loop to skip a render frame.
        target = OUT / "live_monitor_after.png"
        page.screenshot(path=str(target), full_page=True)
        print(f"   saved {target} ({target.stat().st_size // 1024}KB)", file=sys.stderr)

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
