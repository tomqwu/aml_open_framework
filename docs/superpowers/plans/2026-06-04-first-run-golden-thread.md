# First-Run "Golden Thread" Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the confusing cold-open (operational page + 44-page sidebar) with a focused **Start** screen — one sentence, one button — that plays a 4-beat live "Golden Thread" (alert → case → audit) over a real planted case, and fix the broken mobile navigation so the app is usable on a phone.

**Architecture:** A pure, Streamlit-free `dashboard/golden_thread.py` builder shapes four "beats" from plain run records (no pandas → `.[dev]`-testable). A thin full-canvas `pages/0_Start.py` renders the wizard from `st.session_state`. `app.py` makes Start the default landing and routes Skip→Today; the legacy `0_Welcome.py` is retired and folded in. A separate mobile-nav fix corrects the CSS stacking that intercepts the sidebar menu on a phone, backed by an in-canvas "☰ Menu" fallback and a real tap-to-navigate e2e test.

**Tech Stack:** Python 3.10+, Streamlit (pages only), pandas (page layer only — builder is stdlib), pytest, Playwright (e2e). Spec: `docs/superpowers/specs/2026-06-04-first-run-golden-thread-design.md`.

---

## Background facts (verified against the codebase)

- `state.py:initialize_session()` caches into `st.session_state`: `df_alerts`, `df_cases`, `df_decisions`, `df_customers`, `df_txns`, `df_metrics` (all pandas DataFrames), plus `result`, `run_dir`, `spec`, `as_of`. Alert rows are flattened `{"rule_id": rule_id, **alert}` so each carries `customer_id`, `severity`, `sum_amount`/`amount`, `count`, and (when prioritization is on) `priority_score`. Case rows are the raw `cases/*.json` dicts (`case_id`, `customer_id`, `rule_id`, `queue`, `status`, …).
- Planted positive `C0001` is a **structuring** typology (CLAUDE.md). It produces an alert (and a case) in the default dashboard run.
- Page convention tests that any new page must satisfy: `test_dashboard_page_header.py` (module-scope `page_header(...)`), `test_dashboard_page_footer.py` (imports + calls `page_footer()` as the last top-level statement; `page_footer()` immediately precedes every `st.stop()`), `test_section_explainer_migrated_pages.py` (a `section_explainer(` call + the filename pinned in `_EXPECTED_PAGE_LEVEL`), `test_dashboard_tour_coverage.py` (every non-`TOUR_EXEMPT` page has a `### Title` heading in `docs/dashboard-tour.md`; the `**N purpose-built pages**` count == `len(page_files) - len(TOUR_EXEMPT)`).
- `TOUR_EXEMPT = {"0_Welcome.py", "0_Today.py"}` — navigation surfaces excluded from the tour count.
- `app.py` builds `ALL_PAGES: dict[str, list[st.Page]]`; the **first** `st.Page` in nav order is the Streamlit default landing. `0_Today.py` is currently first (in a leading section), `0_Welcome.py` is registered too. Sidebar nav = `st.navigation(visible_pages)`.
- Mobile: `initial_sidebar_state="auto"` collapses the sidebar on narrow viewports; `components.py:414-422` forces the expand control *visible*, but `tests/test_e2e_dashboard_mobile.py:63-70` documents that an overlay **intercepts** the tap, so the mobile e2e navigates by URL slug instead of clicking.
- `.[dev]`-only unit CI has no pandas → any test importing pandas needs `pytest.importorskip("pandas")`. The Golden Thread builder avoids pandas entirely (takes `list[dict]`), so `tests/test_golden_thread.py` needs no skip-guard.

## File Structure

- **Create** `src/aml_framework/dashboard/golden_thread.py` — `Beat` shape + `build_beats(alerts, cases, audit, *, hero=...) -> list[dict]`; pure, stdlib-only, deterministic.
- **Create** `src/aml_framework/dashboard/pages/0_Start.py` — full-canvas wizard renderer.
- **Create** `tests/test_golden_thread.py` — builder unit tests.
- **Modify** `src/aml_framework/dashboard/app.py` — Start first in nav (default landing); Skip→Today wiring lives in the page; remove the `0_Welcome.py` `st.Page`.
- **Delete** `src/aml_framework/dashboard/pages/0_Welcome.py` (fold key copy into Start).
- **Modify** `tests/test_dashboard_tour_coverage.py` — swap `0_Welcome.py`→`0_Start.py` in `TOUR_EXEMPT`.
- **Modify** `tests/test_section_explainer_migrated_pages.py` — swap Welcome→Start pin.
- **Modify** `tests/test_e2e_dashboard.py` + `tests/test_e2e_dashboard_mobile.py` — Welcome→Start; add the mobile tap-to-navigate test.
- **Modify** `src/aml_framework/dashboard/components.py` — mobile z-index/pointer-events fix + (optional) in-canvas Menu helper.
- **Modify** `docs/dashboard-tour.md`, `README.md`, `docs/progress.md`, `src/aml_framework/dashboard/audience.py` (remove any "Welcome" references).

## Beat contract (every task uses this)

```python
# one beat in the Golden Thread
{
    "title": str,         # "The engine caught this."
    "narration": str,     # one plain sentence
    "panel_kind": str,    # "alert" | "case" | "audit" | "doors" | "empty"
    "payload": dict,      # the real record for that panel (alert/case/audit summary)
}
```

---

### Task 1: `golden_thread.py` — pure beat builder

**Files:**
- Create: `src/aml_framework/dashboard/golden_thread.py`
- Test: `tests/test_golden_thread.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_golden_thread.py
from __future__ import annotations

from aml_framework.dashboard.golden_thread import (
    PANEL_ALERT,
    PANEL_AUDIT,
    PANEL_CASE,
    PANEL_DOORS,
    PANEL_EMPTY,
    build_beats,
    pick_hero_alert,
)

_AUDIT = {"decisions_hash": "abc123", "reproducible": True}


def _alert(cid, rule_id="structuring_cash", sev="high", amount=95000, count=12, score=0.8):
    return {
        "customer_id": cid,
        "rule_id": rule_id,
        "severity": sev,
        "sum_amount": amount,
        "count": count,
        "priority_score": score,
    }


def _case(cid, rule_id="structuring_cash"):
    return {"case_id": f"{rule_id}__{cid}", "customer_id": cid, "rule_id": rule_id, "status": "open"}


def test_prefers_planted_c0001():
    alerts = [_alert("C0040", score=0.99), _alert("C0001", score=0.3)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0001"  # planted case wins even at lower score


def test_falls_back_to_highest_priority_when_no_c0001():
    alerts = [_alert("C0040", score=0.4), _alert("C0050", score=0.9)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0050"


def test_falls_back_to_first_alert_when_no_scores():
    alerts = [_alert("C0040", score=None), _alert("C0050", score=None)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0040"


def test_pick_hero_none_when_no_alerts():
    assert pick_hero_alert([]) is None


def test_build_beats_four_beats_with_real_payloads():
    alerts = [_alert("C0001")]
    cases = [_case("C0001")]
    beats = build_beats(alerts, cases, _AUDIT)
    kinds = [b["panel_kind"] for b in beats]
    assert kinds == [PANEL_ALERT, PANEL_CASE, PANEL_AUDIT, PANEL_DOORS]
    assert beats[0]["payload"]["customer_id"] == "C0001"
    assert beats[1]["payload"]["case_id"] == "structuring_cash__C0001"
    assert beats[2]["payload"]["decisions_hash"] == "abc123"
    # every beat has a title + a one-sentence narration
    assert all(b["title"] and b["narration"] for b in beats)


def test_build_beats_case_beat_tolerates_missing_case():
    beats = build_beats([_alert("C0001")], [], _AUDIT)  # alert but no matching case
    assert beats[1]["panel_kind"] == PANEL_CASE
    assert beats[1]["payload"] == {}  # graceful empty, narration still present
    assert beats[1]["narration"]


def test_build_beats_empty_run_yields_friendly_single_beat():
    beats = build_beats([], [], _AUDIT)
    assert len(beats) == 1
    assert beats[0]["panel_kind"] == PANEL_EMPTY
    assert "no alerts" in beats[0]["narration"].lower()


def test_build_beats_is_deterministic():
    a = build_beats([_alert("C0001"), _alert("C0001", rule_id="other")], [_case("C0001")], _AUDIT)
    b = build_beats([_alert("C0001"), _alert("C0001", rule_id="other")], [_case("C0001")], _AUDIT)
    assert a == b
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_golden_thread.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aml_framework.dashboard.golden_thread'`

- [ ] **Step 3: Write the builder**

```python
# src/aml_framework/dashboard/golden_thread.py
"""Pure builder for the first-run Golden Thread (Streamlit-free, stdlib-only).

Selects ONE real planted example from the cached run and shapes it into four
narrated beats — alert -> case -> audit -> doors — that `pages/0_Start.py`
renders full-canvas. No pandas/streamlit import, so it unit-tests under the
`.[dev]`-only CI. Deterministic: same records in -> same beats out.
"""

from __future__ import annotations

from typing import Any

PANEL_ALERT = "alert"
PANEL_CASE = "case"
PANEL_AUDIT = "audit"
PANEL_DOORS = "doors"
PANEL_EMPTY = "empty"

# The canonical first-impression example: planted structuring positive.
_HERO_CUSTOMER = "C0001"


def _score(alert: dict[str, Any]) -> float:
    s = alert.get("priority_score")
    try:
        return float(s)
    except (TypeError, ValueError):
        return -1.0


def pick_hero_alert(alerts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the example alert: prefer the planted C0001 structuring case, else
    the highest priority_score, else the first alert, else None."""
    if not alerts:
        return None
    planted = [a for a in alerts if str(a.get("customer_id")) == _HERO_CUSTOMER]
    if planted:
        return planted[0]
    scored = [a for a in alerts if _score(a) >= 0.0]
    if scored:
        return max(scored, key=_score)
    return alerts[0]


def _case_for(cases: list[dict[str, Any]], alert: dict[str, Any]) -> dict[str, Any]:
    cid = str(alert.get("customer_id"))
    rid = str(alert.get("rule_id"))
    exact = [c for c in cases if str(c.get("customer_id")) == cid and str(c.get("rule_id")) == rid]
    if exact:
        return exact[0]
    any_cid = [c for c in cases if str(c.get("customer_id")) == cid]
    return any_cid[0] if any_cid else {}


def build_beats(
    alerts: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Shape the four-beat Golden Thread from real run records. Falls back to a
    single friendly beat when the run produced no alerts."""
    hero = pick_hero_alert(alerts)
    if hero is None:
        return [
            {
                "title": "A clean run",
                "narration": (
                    "This program produced no alerts on the current data — every "
                    "rule ran and nothing crossed a threshold. Load a spec with "
                    "planted activity to watch the full alert → case → audit story."
                ),
                "panel_kind": PANEL_EMPTY,
                "payload": {},
            }
        ]
    case = _case_for(cases, hero)
    return [
        {
            "title": "The engine caught this.",
            "narration": (
                "A rule flagged a suspicious pattern — here, repeated cash deposits "
                "just under the reporting threshold. Classic structuring."
            ),
            "panel_kind": PANEL_ALERT,
            "payload": hero,
        },
        {
            "title": "Here's the case your team works.",
            "narration": "Everything an investigator needs is already assembled — no hunting across eight tabs.",
            "panel_kind": PANEL_CASE,
            "payload": case,
        },
        {
            "title": "Here's what you hand the regulator.",
            "narration": "Every decision is recorded and replayable byte-for-byte. No six-week reconstruction.",
            "panel_kind": PANEL_AUDIT,
            "payload": dict(audit),
        },
        {
            "title": "Now it's yours.",
            "narration": "Pick the view for your role, or browse the full toolkit.",
            "panel_kind": PANEL_DOORS,
            "payload": {},
        },
    ]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_golden_thread.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Lint + commit**

Run: `ruff check src/aml_framework/dashboard/golden_thread.py tests/test_golden_thread.py && ruff format --check src/aml_framework/dashboard/golden_thread.py tests/test_golden_thread.py`
```bash
git add src/aml_framework/dashboard/golden_thread.py tests/test_golden_thread.py
git commit -m "feat(start): pure Golden Thread beat builder"
```

---

### Task 2: `pages/0_Start.py` — the Start wizard

**Files:**
- Create: `src/aml_framework/dashboard/pages/0_Start.py`

> Covered by the page-convention tests (Task 3 wiring) + e2e (Task 5). Logic lives in `golden_thread.py` (Task 1).

- [ ] **Step 1a: Confirm the audit summary fields available from state**

Run: `python -c "from aml_framework.engine import audit"` then inspect `st.session_state['result'].manifest` keys in a scratch run (the manifest carries `decisions_hash`). Confirm the page can read `decisions_hash` off `st.session_state.result.manifest` and a reproducibility flag (`True` constant is fine — the framework's determinism contract). Adjust the `_audit_summary()` helper in Step 2 if the key differs.

- [ ] **Step 2: Write the page**

```python
# src/aml_framework/dashboard/pages/0_Start.py
"""Start — the first-run front door. One sentence, one button, then a live
4-beat Golden Thread (alert -> case -> audit) over a real planted case.

Full-canvas: it does NOT depend on the sidebar, so it works on a phone even
while the broader nav loads. The 44 pages stay out of sight until the final
beat. ADVISORY/orientation surface only — reads cached run data, changes
nothing.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard import golden_thread as gt
from aml_framework.dashboard.components import page_footer, page_header, section_explainer
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Start here",
    "An anti-money-laundering program you can show your regulator — without a six-week reconstruction.",
)
section_explainer(
    page="Start here",
    section_id="start.page",
    section_title="Start here",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
    },
)

st.caption(
    "You write the rules once. It runs them, builds the cases, and keeps a "
    "tamper-proof record of everything."
)


def _records(key: str) -> list[dict]:
    df = st.session_state.get(key)
    if df is None or getattr(df, "empty", True):
        return []
    return df.to_dict("records")


def _audit_summary() -> dict:
    result = st.session_state.get("result")
    manifest = getattr(result, "manifest", {}) or {}
    return {"decisions_hash": manifest.get("decisions_hash", "—"), "reproducible": True}


beats = gt.build_beats(_records("df_alerts"), _records("df_cases"), _audit_summary())
st.session_state.setdefault("gt_beat", -1)  # -1 = hero (pre-tour) screen
idx = st.session_state["gt_beat"]


def _go(i: int) -> None:
    st.session_state["gt_beat"] = i


if idx < 0:
    # Hero screen: one sentence (header) + one button.
    st.button("▶  Show me it's real (90 seconds)", type="primary", on_click=_go, args=(0,))
    st.page_link("pages/0_Today.py", label="Skip to the app →")
    page_footer()
    st.stop()

beat = beats[min(idx, len(beats) - 1)]
st.subheader(beat["title"])
st.write(beat["narration"])

if beat["panel_kind"] == gt.PANEL_ALERT:
    a = beat["payload"]
    st.metric("Customer", a.get("customer_id", "—"))
    st.json({k: a.get(k) for k in ("rule_id", "severity", "sum_amount", "count", "priority_score")})
elif beat["panel_kind"] == gt.PANEL_CASE:
    if beat["payload"]:
        st.json(beat["payload"])
    else:
        st.info("Case assembly view — open the matching case in Case Investigation.")
elif beat["panel_kind"] == gt.PANEL_AUDIT:
    st.json(beat["payload"])
    st.caption("Verify it yourself: `aml verify-decisions` re-hashes the ledger.")
elif beat["panel_kind"] == gt.PANEL_EMPTY:
    st.info("Load an example spec with planted activity to see the full story.")

# Controls.
if beat["panel_kind"] == gt.PANEL_DOORS:
    st.page_link("pages/0_Today.py", label="Explore for my role →")
    st.page_link("pages/3_Alert_Queue.py", label="Browse all tools →")
    st.button("↻ Replay the tour", on_click=_go, args=(-1,))
elif beat["panel_kind"] != gt.PANEL_EMPTY and idx < len(beats) - 1:
    st.button("Next →", type="primary", on_click=_go, args=(idx + 1,))
    st.button("Skip to the app →", on_click=_go, args=(len(beats) - 1,))
else:
    st.button("↻ Replay the tour", on_click=_go, args=(-1,))

page_footer()
```

- [ ] **Step 3: Byte-compile + lint**

Run: `python -m py_compile src/aml_framework/dashboard/pages/0_Start.py`
Run: `ruff check src/aml_framework/dashboard/pages/0_Start.py && ruff format --check src/aml_framework/dashboard/pages/0_Start.py`
Expected: no output / All checks passed.

- [ ] **Step 4: Commit**

```bash
git add src/aml_framework/dashboard/pages/0_Start.py
git commit -m "feat(start): full-canvas Start wizard rendering the Golden Thread"
```

---

### Task 3: Make Start the default landing; retire Welcome

**Files:**
- Modify: `src/aml_framework/dashboard/app.py`
- Delete: `src/aml_framework/dashboard/pages/0_Welcome.py`
- Modify: `tests/test_dashboard_tour_coverage.py`, `tests/test_section_explainer_migrated_pages.py`, `tests/test_e2e_dashboard.py`, `src/aml_framework/dashboard/audience.py`

- [ ] **Step 1: Register Start first in `app.py` nav**

In `ALL_PAGES`, add `st.Page("pages/0_Start.py", title="Start here", icon=":material/play_circle:")` as the **first** entry of the first section (ahead of Today) so Streamlit lands on it. Remove the `st.Page("pages/0_Welcome.py", ...)` entry. (Step 1a: grep `0_Welcome` in `app.py` to find the exact line.)

- [ ] **Step 2: Delete the legacy Welcome page**

```bash
git rm src/aml_framework/dashboard/pages/0_Welcome.py
```

- [ ] **Step 3: Update the convention-test pins (Welcome → Start)**

- `tests/test_dashboard_tour_coverage.py`: in `TOUR_EXEMPT`, replace `"0_Welcome.py"` with `"0_Start.py"` (Start is a navigation surface, documented separately — keeps the `**N purpose-built pages**` count unchanged).
- `tests/test_section_explainer_migrated_pages.py`: in `_EXPECTED_PAGE_LEVEL`, replace `"0_Welcome.py"` with `"0_Start.py"`.
- `tests/test_e2e_dashboard.py`: in `PAGES`, replace `"Welcome"` with `"Start here"`; in `_PAGE_TO_SECTION`, replace the `"Welcome"` entry with `"Start here": ""` (Start has no section header — it's the leading default like Today). (Step 3a: grep `Welcome` across `tests/` and `src/aml_framework/dashboard/` and update every hit, including `audience.py` if it lists "Welcome".)

- [ ] **Step 4: Run the affected tests**

Run: `python -m pytest tests/test_dashboard_tour_coverage.py tests/test_section_explainer_migrated_pages.py tests/test_dashboard_page_header.py tests/test_dashboard_page_footer.py -q`
Expected: PASS — Start satisfies header/footer/section-explainer; tour count unchanged (Welcome swapped for Start in TOUR_EXEMPT).

> If `test_e2e_dashboard.py::test_all_pages_in_e2e_list` fails, the `PAGES` set must equal the `st.Page` titles parsed from `app.py` — make sure `"Start here"` is in `PAGES` and `"Welcome"` is gone.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(start): default to Start, retire legacy Welcome page"
```

---

### Task 4: Docs — tour entry + counts + README + progress

**Files:**
- Modify: `docs/dashboard-tour.md`, `README.md`

- [ ] **Step 1: Tour doc — replace the Welcome section with Start, keep counts honest**

In `docs/dashboard-tour.md`: if a `### Welcome` section exists, retitle/replace it with a short Start description; ensure the header `**42 purpose-built pages**` and `(44 page files on disk …)` lines still match (deleting Welcome −1 file, adding Start +1 file → 44 files unchanged; both are TOUR_EXEMPT navigation surfaces, so the "42 purpose-built" count is unchanged). (Step 1a: run `python -m pytest tests/test_dashboard_tour_coverage.py -q` and fix counts to whatever the test computes.)

- [ ] **Step 2: README first-impression note**

Add one line under the dashboard section of `README.md`: the app opens on a **Start** screen — one sentence + a 90-second live "Golden Thread" (alert → case → audit) — then hands you the full toolkit.

- [ ] **Step 3: Commit**

```bash
git add docs/dashboard-tour.md README.md
git commit -m "docs(start): document the Start screen + Golden Thread"
```

---

### Task 5: Mobile nav fix — diagnose, fix the native control, in-canvas Menu, tap test

**Files:**
- Modify: `src/aml_framework/dashboard/components.py`
- Modify: `tests/test_e2e_dashboard_mobile.py`

- [ ] **Step 1: Diagnose the interception (empirical)**

Launch the dashboard (`aml dashboard examples/community_bank/aml.yaml --port 8520`) and run a throwaway Playwright probe at 375×667 that (a) locates the sidebar expand control (`[data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"]`), (b) reads `document.elementFromPoint(cx, cy)` at the control's centre, and (c) prints what element is actually on top. Record the offending element (hypothesis: the sticky top-bar/header has a higher `z-index`). This determines the exact CSS target in Step 3.

- [ ] **Step 2: Write the failing mobile e2e tap test**

In `tests/test_e2e_dashboard_mobile.py`, add a test that does NOT use URL-slug nav:

```python
def test_mobile_menu_tap_navigates(self, mobile_page_375):
    page = mobile_page_375
    page.goto(BASE)  # lands on Start (default)
    page.wait_for_selector("h1", state="visible", timeout=20000)
    before = page.url
    # Tap the real menu control a thumb would use.
    ctrl = page.locator(
        "[data-testid='stSidebarCollapsedControl'], [data-testid='stExpandSidebarButton']"
    ).first
    ctrl.click(timeout=8000)  # MUST be tappable — no overlay interception
    page.get_by_role("link", name="Today").first.click(timeout=8000)
    page.wait_for_function("u => location.href !== u", arg=before, timeout=8000)
    assert page.url != before, "mobile menu tap did not navigate — sidebar dead end"
```

(Step 2a: align fixture/name with the file's existing viewport fixtures + `BASE` constant; the file already parametrises 375×667.)

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_e2e_dashboard_mobile.py -k menu_tap -q`
Expected: FAIL — `ctrl.click` times out / no navigation (the overlay interception this fix targets).

- [ ] **Step 4: Fix the stacking in `components.py`**

Target the element identified in Step 1. Add CSS so the sidebar expand control sits above the top-bar and remains hittable on mobile, e.g.:

```css
/* M-NAV: keep the collapsed-sidebar expand control tappable on a phone —
 * the sticky top-bar was painting over it (z-index) and swallowing the tap. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"] {
    z-index: 1000 !important;      /* above the top-bar */
    pointer-events: auto !important;
}
/* Belt-and-braces: stop the top-bar overlay from capturing taps over the
 * control's hit-box on narrow viewports. */
@media (max-width: 640px) {
    [data-testid="stHeader"], .aml-topbar {  /* the offending overlay from Step 1 */
        pointer-events: none;
    }
    [data-testid="stHeader"] a, [data-testid="stHeader"] button { pointer-events: auto; }
}
```

(Replace `.aml-topbar`/`[data-testid="stHeader"]` with the exact selector found in Step 1.)

- [ ] **Step 5: In-canvas Menu fallback (version-proof insurance)**

Add a small helper used at the top of pages on narrow viewports — a compact page-jump that never depends on the sidebar control. Minimal, additive:

```python
# components.py
def mobile_menu(pages: list[tuple[str, str]]) -> None:
    """Render an in-canvas '☰ Menu' page-jump (label, page_path). A version-
    proof nav path that doesn't rely on the Streamlit sidebar expand control."""
    import streamlit as st

    with st.expander("☰ Menu", expanded=False):
        for label, path in pages:
            st.page_link(path, label=label)
```

Wire a short list of the most-used pages into `pages/0_Start.py`'s final beat (and Today) as the guaranteed path. (Keep it to ~6 links — YAGNI; the native fix is the headline.)

- [ ] **Step 6: Run the mobile e2e to verify pass**

Run: `python -m pytest tests/test_e2e_dashboard_mobile.py -k menu_tap -q`
Expected: PASS — a real tap on the control navigates.

- [ ] **Step 7: Lint + commit**

```bash
ruff check src/aml_framework/dashboard/components.py
git add src/aml_framework/dashboard/components.py tests/test_e2e_dashboard_mobile.py
git commit -m "fix(mobile): make the sidebar menu control tappable + in-canvas Menu fallback"
```

---

### Task 6: Full local gate + screenshot + progress entry

- [ ] **Step 1: Dashboard-related unit + convention suite**

Run: `python -m pytest tests/test_golden_thread.py tests/test_dashboard_page_header.py tests/test_dashboard_page_footer.py tests/test_dashboard_tour_coverage.py tests/test_section_explainer_migrated_pages.py "tests/test_e2e_dashboard.py::test_all_pages_in_e2e_list" -q`
Expected: all PASS.

- [ ] **Step 2: Lint the whole change**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: All checks passed.

- [ ] **Step 3: Full unit suite (CI parity)**

Run: `make ci-unit`
Expected: green.

- [ ] **Step 4: e2e — desktop Start render + mobile tap**

Run: `python -m pytest tests/test_e2e_dashboard.py -k "Start or menu" tests/test_e2e_dashboard_mobile.py -q` (or the full e2e if the environment supports the ~15-min run).
Expected: Start renders desktop + the mobile tap navigates.

- [ ] **Step 5: Screenshot the Start screen**

Launch the dashboard, capture the hero + a beat into `docs/screenshots/0_start.png` (mirror `scripts/capture_dashboard_screenshots.py`'s viewport-resize approach). Reference it from `docs/dashboard-tour.md`.

- [ ] **Step 6: progress.md round entry + commit**

Add a `docs/progress.md` entry: the Start/Golden-Thread first-run + mobile-nav fix.
```bash
git add docs/screenshots/0_start.png docs/dashboard-tour.md docs/progress.md
git commit -m "docs(start): Start screenshot + progress entry"
```

---

## Self-Review

**Spec coverage:**
- One-sentence + one-button Start as default landing → Tasks 2 + 3. ✓
- Live 4-beat Golden Thread (alert→case→audit→doors) over C0001 → Tasks 1 + 2. ✓
- 44 pages hidden until Beat 4; Skip→Today → Task 2 (`page_link` to Today) + Task 3. ✓
- Welcome retired/folded; one intro surface → Task 3. ✓
- Mobile native nav genuinely fixed + in-canvas Menu insurance + real tap test → Task 5. ✓
- Error handling (builder fallbacks, never crashes) → Task 1 (tests for missing case / empty run). ✓
- Tests + docs + screenshot + progress → Tasks 4 + 6. ✓

**Placeholder scan:** the two empirical unknowns (audit-summary key in 2·1a; the exact overlay selector in 5·1) carry explicit *verify-first* diagnostic steps with the command to run, not hand-waved logic. All builder/page/CSS code is complete.

**Type consistency:** `build_beats(alerts, cases, audit)` / `pick_hero_alert(alerts)` / the `PANEL_*` constants / the beat dict shape (`title`/`narration`/`panel_kind`/`payload`) are referenced identically in Task 1 (defs + tests) and Task 2 (page). `mobile_menu(pages)` signature matches its Task-5 call site. Page title `"Start here"` is consistent across `app.py`, the e2e `PAGES`/`_PAGE_TO_SECTION`, and the tour doc.

## PR / wrap-up

- Codex review → fix blockers → push → draft PR `Closes` the onboarding issue (file one if none) + checklist + screenshot + mobile-tap evidence.
- Dashboard surface change (new default landing + mobile fix) → **Azure deploy warranted**: bump tag, build, roll both apps, smoke `/` (Start renders) + a 375px check.
