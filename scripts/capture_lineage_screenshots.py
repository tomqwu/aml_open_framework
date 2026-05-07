"""Capture refreshed screenshots after Round 13 lineage breadcrumbs.

Boots a Playwright browser against an already-running Streamlit
dashboard (http://localhost:8506 — same port the existing
capture_pilot_screenshots.py uses) and screenshots:

  - 3_Alert_Queue          (refresh — Matched rows + Rule version columns, PR-LIN-12)
  - 4_Case_Investigation   (refresh — Why this fired panel + deep-link, PR-LIN-12)
  - 7_Audit_Evidence       (refresh — extended lineage walk-back, Round 12+13)
  - 10_Network_Explorer    (refresh — Lineage walk-back per alerted customer, PR-LIN-13)
  - 17_Customer_360        (refresh — Matched rows + Rule version + deep-link, PR-LIN-13)
  - 30_Data_Integration    (refresh — Source → Contract → Table section, Round 12)
  - 32_Lineage_Explorer    (NEW — the dedicated walk-back page, Round 12 PR-LIN-8)

Outputs to docs/screenshots/ (canonical) AND to the two deck-local
asset dirs (deck-v2/assets/screens/, deck-v2/business-slides/
assets/screens/) so the demo decks pick up the new images on the
next `make sync-demo`.

Run sequence:
  Terminal 1:  aml dashboard examples/community_bank/aml.yaml --port 8506
  Terminal 2:  python scripts/capture_lineage_screenshots.py

Or use the wrapper at the bottom that boots + captures + tears down
in one process.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs" / "screenshots"
DECK_TECH = ROOT / "docs" / "pitch" / "deck-v2" / "assets" / "screens"
DECK_BIZ = ROOT / "docs" / "pitch" / "deck-v2" / "business-slides" / "assets" / "screens"

# (URL slug, output filename, description, deck destination set)
# Slug is Streamlit's multi-page route — file's display name (drop
# the numeric prefix, keep the underscores).
PAGES: list[tuple[str, str, str, set[str]]] = [
    ("Alert_Queue", "03_alert_queue.png", "Alert Queue", {"tech", "biz"}),
    ("Case_Investigation", "04_case_investigation.png", "Case Investigation", {"tech", "biz"}),
    ("Audit_Evidence", "07_audit_evidence.png", "Audit & Evidence", {"tech"}),
    ("Network_Explorer", "10_network_explorer.png", "Network Explorer", {"tech", "biz"}),
    ("Customer_360", "17_customer_360.png", "Customer 360", {"biz"}),
    ("Data_Integration", "30_data_integration.png", "Data Integration", {"tech"}),
    ("Lineage_Explorer", "32_lineage_explorer.png", "Lineage Explorer", {"tech", "biz"}),
]

PORT = 8506


def main() -> int:
    from playwright.sync_api import sync_playwright

    CANONICAL.mkdir(parents=True, exist_ok=True)
    DECK_TECH.mkdir(parents=True, exist_ok=True)
    DECK_BIZ.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1600, "height": 2400})
        page = ctx.new_page()

        # Prime: navigate to the root once so app.py's
        # initialize_session() runs and seeds session_state. Without
        # this, direct page-URL navigation can race the bootstrap and
        # the page script reads from un-initialized session state.
        print(f"▶ Priming session via http://localhost:{PORT}/", file=sys.stderr)
        page.goto(f"http://localhost:{PORT}/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(8000)

        for slug, fname, label, deck_set in PAGES:
            url = f"http://localhost:{PORT}/{slug}"
            print(f"▶ Capturing {label} ({url})", file=sys.stderr)
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                print(f"  ✗ goto failed: {e}", file=sys.stderr)
                continue

            # Streamlit pages settle slowly — give charts + AG Grid
            # time to hydrate. Scroll-cycle so any sticky chrome
            # repositions correctly.
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800)

            target = CANONICAL / fname
            page.screenshot(path=str(target), full_page=True)
            size_kb = target.stat().st_size // 1024
            print(f"  ✓ {target.relative_to(ROOT)} ({size_kb}KB)", file=sys.stderr)

            # Mirror to deck-local asset dirs.
            if "tech" in deck_set:
                shutil.copyfile(target, DECK_TECH / fname)
            if "biz" in deck_set:
                shutil.copyfile(target, DECK_BIZ / fname)

        browser.close()

    print(f"\n✓ Done. {len(PAGES)} screenshots refreshed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
