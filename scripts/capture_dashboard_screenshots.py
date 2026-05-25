"""Regenerate every dashboard tour screenshot from a live `aml dashboard`.

PR-DOCS-5: the R31 IA refactor + R32 Knowledge retirement + the C-layout
level-2 nav + sidebar docs links shipped without re-capturing the
screenshots in `docs/screenshots/`. Every existing PNG predates those
changes (newest is 2026-05-18). This script walks the operational
tour, navigates to each page, and writes a fresh capture.

Usage:

    # in one terminal:
    aml dashboard examples/community_bank/aml.yaml --port 8506

    # in another:
    python scripts/capture_dashboard_screenshots.py

The script does NOT spin up the dashboard itself — that's the caller's
job. Lets you eyeball the live UI in the browser while the captures
write, and avoids the eternal "did Streamlit actually finish bootstrapping?"
sleep-loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
BASE = "http://localhost:8506"

# (filename without .png, dashboard URL slug). Slug rules:
# - Title-derived: `title.replace(" & ", "_").replace(" ", "_")`
# - Some pages pin `url_path=` explicitly (see app.py); follow those.
# Mirrors the historical filenames so dashboard-tour.md's
# `![Foo](screenshots/NN_foo.png)` refs keep resolving.
PAGES: list[tuple[str, str]] = [
    ("00_today", ""),  # root resolves to Today
    ("01_executive_dashboard", "Executive_Dashboard"),
    ("02_program_maturity", "Program_Maturity"),
    ("03_alert_queue", "Alert_Queue"),
    ("04_case_investigation", "Case_Investigation"),
    ("05_rule_performance", "Rule_Performance"),
    ("06_risk_assessment", "Risk_Assessment"),
    # The Streamlit slug for "Audit & Evidence" replaces " & " with "_"
    # → /Audit_Evidence (not /Audit_&_Evidence; that 404s and falls
    # back to Today). Verified by `tests/test_e2e_dashboard.py`'s
    # title-slug helper.
    ("07_audit_evidence", "Audit_Evidence"),
    ("08_framework_alignment", "Framework_Alignment"),
    ("09_transformation_roadmap", "Transformation_Roadmap"),
    ("10_network_explorer", "Network_Explorer"),
    ("11_live_monitor", "Live_Monitor"),
    ("12_sanctions_screening", "Sanctions_Screening"),
    ("13_model_performance", "Model_Performance"),
    ("14_data_quality", "Data_Quality"),
    ("15_run_history", "Run_History"),
    ("16_rule_tuning", "Rule_Tuning"),
    ("17_customer_360", "Customer_360"),
    ("18_typology_catalogue", "Typology_Catalogue"),
    ("19_comparative_analytics", "Comparative_Analytics"),
    ("20_spec_editor", "Spec_Editor"),
    ("21_my_queue", "My_Queue"),
    ("22_analyst_review_queue", "Analyst_Review_Queue"),
    ("23_tuning_lab", "Tuning_Lab"),
    ("24_investigations", "Investigations"),
    ("25_boi_workflow", "BOI_Workflow"),
    ("26_fintech_cockpit", "FinTech_Cockpit"),
    ("27_regulator_pulse", "Regulator_Pulse"),
    ("28_metrics_taxonomy", "Metrics_Taxonomy"),
    ("29_ai_assistant", "AI_Assistant"),
    ("30_data_integration", "Data_Integration"),
    ("31_information_sharing", "Information_Sharing"),
    ("32_lineage_explorer", "Lineage_Explorer"),
    # R26+ universally-routed surfaces — no historical captures.
    ("43_north_star_coverage", "North-Star_Pillar_Coverage"),
    ("44_decision_trail", "Decision_Trail"),
    ("45_fp_analysis", "FP_Analysis"),
    ("46_experiment_tracking", "Experiment_Tracking"),
    ("47_threshold_sensitivity", "Threshold_Sensitivity"),
    ("48_equivalence", "Equivalence"),
    ("49_anomaly_discovery", "Anomaly_Discovery"),
    ("50_drift_monitor", "Drift_Monitor"),
    ("51_rule_lifecycle", "Rule_Lifecycle"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    captured = 0
    failed: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Streamlit scrolls INSIDE its app container, so Playwright's
        # `full_page=True` is bounded by the viewport height. Strategy:
        # start with a sane initial viewport, navigate + wait, then read
        # the actual `document.documentElement.scrollHeight` and resize
        # the viewport to that exact size + a small margin before
        # screenshotting. Codex P2 rounds 2-3: a static 1440x900 produced
        # above-the-fold crops; a static 1440x3200 still clipped the
        # 8-pillar North-Star page. Dynamic sizing is the correct fix.
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        for name, slug in PAGES:
            url = f"{BASE}/{slug}" if slug else BASE
            try:
                # Reset to the small viewport between pages so scrollHeight
                # measurement reflects the page's natural layout (not the
                # previous page's expanded canvas).
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(url, wait_until="load", timeout=30000)
                # Wait for Streamlit page hero (`page_header(...)` → <h1>)
                page.wait_for_selector(
                    "[data-testid='stHeading'], h1", state="visible", timeout=20000
                )
                # Settle async section-explainer AI panels + chart paint
                page.wait_for_timeout(1500)
                # Streamlit scrolls inside `[data-testid="stMain"]` —
                # NOT `document.documentElement` (which always equals the
                # viewport). The real content height is `stMain.scrollHeight`.
                # Codex P2 round 4: querying `document` returned 900 for
                # every page, so the dynamic-resize fix was a no-op and
                # long pages stayed clipped. Probed locally: North-Star
                # page reports `stMain.scrollHeight = 6178` (8 pillars
                # rendered) versus `document.scrollHeight = 900`. Pull
                # from stMain; fall back to document if the selector ever
                # changes upstream. `+ 80` for footer margin. Clamp at
                # 16000 to bound runaway charts to a 16k-tall PNG.
                scroll_h = page.evaluate(
                    """() => {
                        const main = document.querySelector('[data-testid="stMain"]');
                        return main ? main.scrollHeight : document.documentElement.scrollHeight;
                    }"""
                )
                viewport_h = min(max(int(scroll_h) + 80, 900), 16000)
                page.set_viewport_size({"width": 1440, "height": viewport_h})
                # Give layout one more tick to reflow under the new viewport.
                page.wait_for_timeout(400)
                target = OUT / f"{name}.png"
                page.screenshot(path=str(target), full_page=True)
                size_kb = target.stat().st_size // 1024
                print(f"  ✓ {name:35s} {viewport_h:5d}h  {size_kb:5d} KB")
                captured += 1
            except Exception as exc:
                print(f"  ✗ {name:35s} FAILED: {exc.__class__.__name__}: {exc}")
                failed.append(name)
        browser.close()
    print(f"\n{captured}/{len(PAGES)} captured", end="")
    if failed:
        print(f", {len(failed)} failed: {failed}")
        return 1
    print(".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
