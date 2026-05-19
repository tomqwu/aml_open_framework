"""Capture responsive before/after screenshots — PR-M1 review evidence.

Throwaway capture script for the responsive-redesign epic. Mirrors the
pattern of `scripts/capture_pilot_screenshots.py` /
`capture_lineage_screenshots.py`: boots a Playwright browser against an
*already-running* Streamlit dashboard and writes PNGs. NOT wired into
the test suite — it produces the visual diff a reviewer eyeballs
alongside the `test_e2e_dashboard_mobile.py` regression net.

The 8 highest-mobile-risk archetype pages are each shot at four
viewports:

    1440x900   desktop baseline
    375x667    iPhone SE   (full-net tier)
    414x896    iPhone XR
    768x1024   iPad portrait

Output:

    docs/screenshots/responsive/<before|after>/<page>__<viewport>.png

`<before|after>` is the first CLI arg (default: "before"). Capture the
"before" set on `main` (thin overlay), the "after" set on each
PR-M2..M6 branch, and diff the pair to prove the responsive work.

Navigation is by Streamlit multi-page URL slug (title with " & " →
"_" and spaces → "_"), mirroring the proven desktop e2e `_navigate`
and `test_e2e_dashboard_mobile.py`. Sidebar-click nav is broken on a
phone viewport here (the fixed `.dna-topbar` overlay intercepts the
collapsed-sidebar expand control), so URL routing is used instead.

Run sequence:
  Terminal 1:  aml dashboard examples/canadian_schedule_i_bank/aml.yaml --port 8506
  Terminal 2:  python scripts/capture_responsive_baseline.py before
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs" / "screenshots" / "responsive"

PORT = 8506

# (nav title, filename slug) — the 8 archetypes the regression net covers.
PAGES: list[tuple[str, str]] = [
    ("Today", "today"),
    ("Executive Dashboard", "executive_dashboard"),
    ("Alert Queue", "alert_queue"),
    ("Audit & Evidence", "audit_evidence"),
    ("Sanctions Screening", "sanctions_screening"),
    ("Customer 360", "customer_360"),
    ("Data Integration", "data_integration"),
    ("Network Explorer", "network_explorer"),
]

VIEWPORTS: list[tuple[str, dict[str, int]]] = [
    ("1440x900", {"width": 1440, "height": 900}),
    ("375x667", {"width": 375, "height": 667}),
    ("414x896", {"width": 414, "height": 896}),
    ("768x1024", {"width": 768, "height": 1024}),
]


def _nav_to(page, title: str) -> None:
    """Navigate to `title` by its Streamlit multi-page URL slug
    (" & " → "_", spaces → "_"). See the module docstring for why
    URL routing is used over sidebar clicks on phone viewports."""
    slug = title.replace(" & ", "_").replace(" ", "_")
    page.goto(
        f"http://localhost:{PORT}/{slug}",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
    page.wait_for_timeout(3500)


def main() -> int:
    subdir = sys.argv[1] if len(sys.argv) > 1 else "before"
    if subdir not in ("before", "after"):
        print(f"usage: {Path(sys.argv[0]).name} [before|after]", file=sys.stderr)
        return 2

    out_dir = OUT_ROOT / subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    shot_count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_label, viewport in VIEWPORTS:
            ctx = browser.new_context(viewport=viewport)
            page = ctx.new_page()
            print(f"▶ Priming {vp_label} via http://localhost:{PORT}/", file=sys.stderr)
            page.goto(f"http://localhost:{PORT}/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
            page.wait_for_timeout(8000)  # engine warm-up on first load

            for title, slug in PAGES:
                print(f"▶ {subdir}/{slug}__{vp_label} — {title}", file=sys.stderr)
                try:
                    _nav_to(page, title)
                except Exception as e:  # noqa: BLE001
                    print(f"  ✗ nav failed: {e}", file=sys.stderr)
                    continue
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(800)
                target = out_dir / f"{slug}__{vp_label}.png"
                page.screenshot(path=str(target), full_page=True)
                size_kb = target.stat().st_size // 1024
                print(f"  ✓ {target.relative_to(ROOT)} ({size_kb}KB)", file=sys.stderr)
                shot_count += 1

            ctx.close()
        browser.close()

    print(f"\n✓ Done. {shot_count} screenshots → {out_dir.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
