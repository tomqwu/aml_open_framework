# M1 — Triage Queue (N1 follow-on) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dashboard "Triage Queue" page that sorts scored alerts by the N1 advisory `priority_score` (desc) and shows the per-alert `priority_explanation`, so investigators can work the highest-risk alerts first.

**Architecture:** Pure, Streamlit-free helper module (`dashboard/triage.py`) holds all sort/format logic so it is unit-testable under the `.[dev]`-only CI (CLAUDE.md lazy-import rule). A thin Streamlit page (`pages/52_Triage_Queue.py`) renders it with the existing `data_grid` component and a per-alert explanation panel. The page is routed **universally** (like North-Star / FP Analysis) to avoid disturbing the `MAX_PAGES_PER_PERSONA=9` cap. Advisory only — re-orders a queue, never changes disposition (mirrors the N1 governance contract).

**Tech Stack:** Python 3.10+, pandas, Streamlit (page only), pytest. Reuses `dashboard/data_grid.py` (AG Grid) and `dashboard/state.py` (`st.session_state.df_alerts`).

---

## Background facts (verified against the codebase)

- Alerts reach the dashboard as `st.session_state.df_alerts` — a flattened `pd.DataFrame` built in `state.py` as `{"rule_id": rule_id, **alert}` per alert. When N1 prioritization is enabled, every alert dict carries `priority_score` (float 0–1) and `priority_explanation` (`list[{feature, value, contribution}]`), so they appear as DataFrame columns. When disabled, those columns are absent.
- `priority_explanation` shape (from `engine/prioritization.py`): a list whose first entry is `{"feature": "bias", "value": 1.0, "contribution": -1.0}` followed by one entry per feature `{"feature": <name>, "value": <0-1>, "contribution": <weight*value>}`. `score == sigmoid(sum(contribution))`.
- `data_grid(df, *, key, severity_col=None, gradient_cols=None, gradient_invert=False, pinned_left=None, drill_target=None, drill_param=None, drill_column=None, height=400, hint=None, ...)` — `dashboard/data_grid.py:99`. `gradient_cols` colours numeric columns red→amber→green; `gradient_invert=True` flips it so **high = red** (urgent), which is what we want for `priority_score`.
- `page_header(title, description=None, *, render_chrome=True)` and `page_footer()` — `dashboard/components.py`; both re-exported and imported as `from aml_framework.dashboard.components import page_header, page_footer, data_grid`.
- Page convention tests (auto-apply to any new page, no edits needed): `tests/test_dashboard_page_header.py` (every page calls `page_header(...)` at module scope), `tests/test_dashboard_page_footer.py` (every page imports + calls `page_footer()` as the **last** top-level statement, and every `st.stop()` is immediately preceded by `page_footer()`).
- `tests/test_dashboard_tour_coverage.py` asserts: every non-exempt page file has a `### <Title>` heading in `docs/dashboard-tour.md`; the header phrase `**N purpose-built pages**` equals `len(page_files) - 2`; and `"{len(AUDIENCE_PAGES)} distinct personas"` appears. Page files today = 43 (excludes `__init__.py`) → header says **41**. Adding one page → **42**, and "(43 page files on disk…)" → "(44 …)".
- `tests/test_e2e_dashboard.py` keeps a `PAGES` list (sidebar order) auto-synced against `app.py`'s `st.Page` titles, plus a `_PAGE_TO_SECTION` map. A new page must be added to both, section `"Operations"`.

## File Structure

- **Create** `src/aml_framework/dashboard/triage.py` — pure helpers (no `streamlit` import): `PRIORITY_COL`, `EXPLANATION_COL`, `DISPLAY_COLS`, `has_priority(df)`, `triage_view(df)`, `explanation_rows(explanation)`, `alert_label(row)`.
- **Create** `src/aml_framework/dashboard/pages/52_Triage_Queue.py` — thin Streamlit page.
- **Create** `tests/test_triage.py` — unit tests for the helpers.
- **Modify** `src/aml_framework/dashboard/audience.py` — add `TRIAGE_PAGES = ["Triage Queue"]`.
- **Modify** `src/aml_framework/dashboard/app.py` — import `TRIAGE_PAGES`, `relevant_titles.update(TRIAGE_PAGES)`, and add the `st.Page(...)` under `"Operations"` in `ALL_PAGES`.
- **Modify** `docs/dashboard-tour.md` — add `### Triage Queue` section under Operational Pages; bump counts 41→42 and 43→44 (and the prose "41 operational pages" → "42").
- **Modify** `tests/test_e2e_dashboard.py` — add `"Triage Queue"` to `PAGES` and `_PAGE_TO_SECTION`.

---

### Task 1: Pure helper module `triage.py`

**Files:**
- Create: `src/aml_framework/dashboard/triage.py`
- Test: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_triage.py
from __future__ import annotations

import math

import pandas as pd

from aml_framework.dashboard import triage


def _df(rows):
    return pd.DataFrame(rows)


def test_has_priority_true_when_column_present_and_scored():
    df = _df([{"rule_id": "r1", "customer_id": "C1", "priority_score": 0.8}])
    assert triage.has_priority(df) is True


def test_has_priority_false_when_column_absent():
    df = _df([{"rule_id": "r1", "customer_id": "C1"}])
    assert triage.has_priority(df) is False


def test_has_priority_false_when_empty():
    assert triage.has_priority(pd.DataFrame()) is False


def test_triage_view_sorted_desc_and_drops_unscored():
    df = _df(
        [
            {"rule_id": "r1", "customer_id": "C1", "severity": "low", "priority_score": 0.2},
            {"rule_id": "r2", "customer_id": "C2", "severity": "high", "priority_score": 0.9},
            {"rule_id": "r3", "customer_id": "C3", "severity": "high"},  # unscored -> NaN
        ]
    )
    view = triage.triage_view(df)
    scores = list(view["priority_score"])
    assert scores == sorted(scores, reverse=True)  # descending
    assert scores[0] == 0.9
    assert len(view) == 2  # the unscored row is dropped


def test_triage_view_stable_tiebreak_on_rule_then_customer():
    df = _df(
        [
            {"rule_id": "rB", "customer_id": "C2", "priority_score": 0.5},
            {"rule_id": "rA", "customer_id": "C9", "priority_score": 0.5},
            {"rule_id": "rA", "customer_id": "C1", "priority_score": 0.5},
        ]
    )
    view = triage.triage_view(df)
    pairs = list(zip(view["rule_id"], view["customer_id"]))
    assert pairs == [("rA", "C1"), ("rA", "C9"), ("rB", "C2")]


def test_explanation_rows_sorted_by_abs_contribution_desc_excludes_bias_signless():
    explanation = [
        {"feature": "bias", "value": 1.0, "contribution": -1.0},
        {"feature": "severity", "value": 0.75, "contribution": 0.75},
        {"feature": "amount", "value": 0.10, "contribution": 0.05},
        {"feature": "volume", "value": 0.40, "contribution": 0.20},
    ]
    rows = triage.explanation_rows(explanation)
    feats = [r["feature"] for r in rows]
    # bias kept first (it's the baseline), then features by |contribution| desc
    assert feats[0] == "bias"
    assert feats[1:] == ["severity", "volume", "amount"]


def test_explanation_rows_handles_empty():
    assert triage.explanation_rows(None) == []
    assert triage.explanation_rows([]) == []


def test_alert_label_format():
    row = {"customer_id": "C1", "rule_id": "r1", "priority_score": 0.873}
    assert triage.alert_label(row) == "C1 · r1 · 0.87"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_triage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'aml_framework.dashboard.triage'`

- [ ] **Step 3: Write the helper module**

```python
# src/aml_framework/dashboard/triage.py
"""Pure helpers for the Triage Queue dashboard page.

Streamlit-free on purpose (CLAUDE.md lazy-import rule: dashboard helper
modules must not import `streamlit` at module level so they unit-test under
the `.[dev]`-only CI). All sort/format logic for the advisory N1
`priority_score` lives here; `pages/52_Triage_Queue.py` is a thin renderer.

ADVISORY: this only re-orders a view of alerts by SAR-likelihood — it never
changes an alert's disposition, queue, or open/close state.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

PRIORITY_COL = "priority_score"
EXPLANATION_COL = "priority_explanation"

# Columns to surface in the queue table, in display order, when present.
DISPLAY_COLS = [
    PRIORITY_COL,
    "rule_id",
    "customer_id",
    "severity",
    "amount",
    "sum_amount",
    "count",
]


def has_priority(df: pd.DataFrame) -> bool:
    """True when the alert frame carries at least one non-null priority_score."""
    if df is None or df.empty or PRIORITY_COL not in df.columns:
        return False
    return bool(df[PRIORITY_COL].notna().any())


def triage_view(df: pd.DataFrame) -> pd.DataFrame:
    """Scored alerts sorted by priority_score desc, with a deterministic
    (rule_id, customer_id) tiebreak. Rows without a score are dropped so the
    queue only shows what the model actually ranked."""
    scored = df[df[PRIORITY_COL].notna()].copy()
    tiebreak = [c for c in ("rule_id", "customer_id") if c in scored.columns]
    scored = scored.sort_values(
        by=[PRIORITY_COL, *tiebreak],
        ascending=[False, *([True] * len(tiebreak))],
        kind="mergesort",  # stable
    ).reset_index(drop=True)
    return scored


def explanation_rows(explanation: Any) -> list[dict[str, Any]]:
    """Normalise a priority_explanation into display rows: the `bias` baseline
    first, then features ordered by absolute contribution (the biggest drivers
    on top). Returns [] for missing/empty input."""
    if not isinstance(explanation, list) or not explanation:
        return []
    bias = [e for e in explanation if e.get("feature") == "bias"]
    feats = [e for e in explanation if e.get("feature") != "bias"]
    feats.sort(key=lambda e: abs(float(e.get("contribution", 0.0))), reverse=True)
    out: list[dict[str, Any]] = []
    for e in [*bias, *feats]:
        out.append(
            {
                "feature": e.get("feature"),
                "value": round(float(e.get("value", 0.0)), 4),
                "contribution": round(float(e.get("contribution", 0.0)), 4),
            }
        )
    return out


def alert_label(row: Any) -> str:
    """Selectbox label for one scored alert: `<customer> · <rule> · <score>`."""
    cid = row.get("customer_id", "—") if hasattr(row, "get") else row["customer_id"]
    rid = row.get("rule_id", "—") if hasattr(row, "get") else row["rule_id"]
    score = float(row["priority_score"]) if hasattr(row, "__getitem__") else 0.0
    return f"{cid} · {rid} · {score:.2f}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_triage.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Lint**

Run: `ruff check src/aml_framework/dashboard/triage.py tests/test_triage.py && ruff format --check src/aml_framework/dashboard/triage.py tests/test_triage.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/dashboard/triage.py tests/test_triage.py
git commit -m "feat(triage): pure helpers for Triage Queue (sort + explanation)"
```

---

### Task 2: The Triage Queue page

**Files:**
- Create: `src/aml_framework/dashboard/pages/52_Triage_Queue.py`

> No unit test here — Streamlit pages are covered by the convention tests (Task 5) + e2e (Task 6). The testable logic already lives in `triage.py` (Task 1).

- [ ] **Step 1: Write the page**

```python
# src/aml_framework/dashboard/pages/52_Triage_Queue.py
"""Triage Queue — sort alerts by the advisory N1 priority_score.

ADVISORY ONLY: this page re-orders a view of alerts by SAR-likelihood so an
investigator can work the highest-risk first. It never changes an alert's
disposition, queue, or open/close state — the deterministic rules stay
authoritative (governed-augmentation thesis).
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard import triage
from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import data_grid, page_footer, page_header
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Triage Queue",
    "Work the highest-risk alerts first — sorted by the advisory priority score.",
)
show_audience_context("Triage Queue")

st.caption(
    "⚖️ **Advisory only.** The priority score re-orders this queue by "
    "SAR-likelihood; it never changes an alert's disposition or open/close "
    "state. Deterministic rules remain authoritative."
)

df_alerts = st.session_state.df_alerts

if df_alerts.empty:
    st.info("No alerts in this run.")
    page_footer()
    st.stop()

if not triage.has_priority(df_alerts):
    st.warning(
        "Alert prioritization is not enabled for this program. Add a "
        "`program.prioritization` block (enabled: true) to the spec to rank "
        "alerts by SAR-likelihood. See the N1 governed alert-prioritization layer."
    )
    page_footer()
    st.stop()

view = triage.triage_view(df_alerts)
available = [c for c in triage.DISPLAY_COLS if c in view.columns]

st.subheader(f"{len(view)} scored alerts")
data_grid(
    view[available],
    key="triage_queue_table",
    severity_col="severity" if "severity" in available else None,
    gradient_cols=[triage.PRIORITY_COL],
    gradient_invert=True,  # high score = red = urgent
    pinned_left=[triage.PRIORITY_COL],
    drill_target="pages/17_Customer_360.py" if "customer_id" in available else None,
    drill_param="customer_id",
    drill_column="customer_id",
    height=420,
    hint="Click a row to open the customer's 360 view. Sort is advisory.",
)

st.divider()
st.subheader("Why this score?")
labels = [triage.alert_label(r) for _, r in view.iterrows()]
choice = st.selectbox("Pick a scored alert to see its explanation", labels, index=0)
selected = view.iloc[labels.index(choice)]
rows = triage.explanation_rows(selected.get(triage.EXPLANATION_COL))
if rows:
    st.caption(
        "score = sigmoid(Σ contributions). Largest absolute contributions first."
    )
    st.dataframe(rows, hide_index=True, use_container_width=True)
else:
    st.caption("No explanation recorded for this alert.")

page_footer()
```

- [ ] **Step 2: Byte-compile to catch syntax errors**

Run: `python -m py_compile src/aml_framework/dashboard/pages/52_Triage_Queue.py`
Expected: no output (exit 0)

- [ ] **Step 3: Lint**

Run: `ruff check src/aml_framework/dashboard/pages/52_Triage_Queue.py && ruff format --check src/aml_framework/dashboard/pages/52_Triage_Queue.py`
Expected: All checks passed

- [ ] **Step 4: Commit**

```bash
git add src/aml_framework/dashboard/pages/52_Triage_Queue.py
git commit -m "feat(triage): Triage Queue dashboard page (advisory priority sort)"
```

---

### Task 3: Register the page (audience + app navigation)

**Files:**
- Modify: `src/aml_framework/dashboard/audience.py`
- Modify: `src/aml_framework/dashboard/app.py:5-18` (imports) and `app.py:77` (Operations) and `app.py:~341` (relevant_titles)

- [ ] **Step 1: Add the universal-routing constant to `audience.py`**

Append after the `LIFECYCLE_PAGES = [...]` block (near line 421):

```python
# M1 (N1 follow-on). Triage Queue ranks alerts by the advisory N1
# priority_score. It's a cross-cutting investigator surface (analysts,
# managers, MLROs, examiners all benefit), so it's routed UNIVERSALLY via
# the same idiom as NORTH_STAR_PAGES / TUNING_PAGES (app.py adds these
# titles to the visible set for every persona), NOT via AUDIENCE_PAGES —
# that preserves MAX_PAGES_PER_PERSONA=9 for the operational arcs.
TRIAGE_PAGES = [
    "Triage Queue",
]
```

- [ ] **Step 2: Import + apply it in `app.py`**

In the `from aml_framework.dashboard.audience import (...)` block (lines 7-17), add `TRIAGE_PAGES,` in alphabetical position (after `TRACKING_PAGES,`, before `TUNING_PAGES,`):

```python
    TRACKING_PAGES,
    TRIAGE_PAGES,
    TUNING_PAGES,
```

After the `relevant_titles.update(EQUIVALENCE_PAGES)` line (~341), add:

```python
    # M1 (N1 follow-on) — Triage Queue advisory priority-sort surface.
    relevant_titles.update(TRIAGE_PAGES)
```

- [ ] **Step 3: Add the page to `ALL_PAGES["Operations"]`**

In `app.py`, inside the `"Operations": [ ... ]` list (after the `11_Live_Monitor.py` entry, before the closing `],` near line 98):

```python
        st.Page(
            "pages/52_Triage_Queue.py",
            title="Triage Queue",
            icon=":material/sort:",
        ),
```

- [ ] **Step 4: Lint**

Run: `ruff check src/aml_framework/dashboard/audience.py src/aml_framework/dashboard/app.py && ruff format --check src/aml_framework/dashboard/audience.py src/aml_framework/dashboard/app.py`
Expected: All checks passed

- [ ] **Step 5: Verify imports resolve (no Streamlit needed for audience)**

Run: `python -c "from aml_framework.dashboard.audience import TRIAGE_PAGES; print(TRIAGE_PAGES)"`
Expected: `['Triage Queue']`

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/dashboard/audience.py src/aml_framework/dashboard/app.py
git commit -m "feat(triage): register Triage Queue (universal routing + Operations nav)"
```

---

### Task 4: Docs — dashboard tour entry + counts

**Files:**
- Modify: `docs/dashboard-tour.md`

- [ ] **Step 1: Bump the header counts**

Find line 3 (`The Streamlit dashboard … across **41 purpose-built pages** (43 page files on disk …`). Replace `**41 purpose-built pages**` with `**42 purpose-built pages**` and `43 page files on disk` with `44 page files on disk`.

- [ ] **Step 2: Bump the audience-filtering prose count**

Find (line ~308) `The 41 operational pages serve 13 distinct personas.` Replace `The 41 operational pages` with `The 42 operational pages`. (Leave `13 distinct personas` unchanged — Triage Queue is universally routed, no new persona.)

- [ ] **Step 3: Add the per-page tour section**

Under `## Operational Pages`, after the `### Alert Queue` section, add:

```markdown
### Triage Queue

Ranks scored alerts by the advisory N1 `priority_score` (highest first) so an
investigator works the highest-SAR-likelihood alerts before the long tail. Each
row's score is colour-graded (red = urgent); a "Why this score?" panel renders
the per-alert `priority_explanation` — the bias baseline plus each feature's
contribution, largest first, with `score = sigmoid(Σ contributions)`. **Advisory
only:** the sort never changes an alert's disposition or open/close state; the
deterministic rules stay authoritative. Routed universally so every investigator
persona can reach it. Enabled by a `program.prioritization` block in the spec.
```

- [ ] **Step 4: Run the tour-coverage test**

Run: `python -m pytest tests/test_dashboard_tour_coverage.py -q`
Expected: PASS (3 passed) — the `### Triage Queue` heading + `**42 purpose-built pages**` now match.

- [ ] **Step 5: Commit**

```bash
git add docs/dashboard-tour.md
git commit -m "docs(tour): add Triage Queue page + bump page counts"
```

---

### Task 5: Convention tests (page header / footer)

**Files:** none (the page must already satisfy `test_dashboard_page_header.py` + `test_dashboard_page_footer.py`).

- [ ] **Step 1: Run the page convention tests**

Run: `python -m pytest tests/test_dashboard_page_header.py tests/test_dashboard_page_footer.py -q`
Expected: PASS. The page calls `page_header(...)` at module scope, imports + calls `page_footer()` as the last top-level statement, and each `st.stop()` (in the two empty-state branches) is immediately preceded by `page_footer()`.

- [ ] **Step 2: If footer test fails on the `st.stop()` rule**

The two early-exit branches in Task 2 already place `page_footer()` immediately before `st.stop()`. If the test flags ordering, ensure both branches read exactly:

```python
    page_footer()
    st.stop()
```

No commit (no file change unless a fix was needed; if so, `git commit --amend` into Task 2's commit is fine before pushing).

---

### Task 6: e2e dashboard registration

**Files:**
- Modify: `tests/test_e2e_dashboard.py`

- [ ] **Step 1: Add to the `PAGES` list**

In `tests/test_e2e_dashboard.py`, add `"Triage Queue"` to the `PAGES` list in the position matching the sidebar order (Operations section — after `"Live Monitor"`):

```python
    "Live Monitor",
    "Triage Queue",
```

- [ ] **Step 2: Add to `_PAGE_TO_SECTION`**

```python
    "Triage Queue": "Operations",
```

- [ ] **Step 3: Run the e2e auto-sync check (fast, no browser)**

Run: `python -m pytest tests/test_e2e_dashboard.py -q -k "list or sync or registered" 2>&1 | tail -15`
Expected: the `PAGES`-vs-`app.py` sync test passes (it parses `app.py` `st.Page` titles and asserts they equal `PAGES`). If a browser-driven test is collected and skipped without Playwright, that's fine.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_dashboard.py
git commit -m "test(e2e): register Triage Queue page in dashboard e2e coverage"
```

---

### Task 7: Full local gate + screenshot

- [ ] **Step 1: Run the dashboard-related unit suite**

Run: `python -m pytest tests/test_triage.py tests/test_dashboard_page_header.py tests/test_dashboard_page_footer.py tests/test_dashboard_tour_coverage.py -q`
Expected: all PASS.

- [ ] **Step 2: Lint the whole change**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: All checks passed

- [ ] **Step 3: Launch the dashboard and capture a Triage Queue screenshot**

Use a spec with prioritization enabled (or temporarily enable it) and the `run` skill / `aml dashboard` to confirm the page renders: queue sorted by `priority_score`, gradient colouring, and the explanation panel populated. Save the screenshot under `docs/screenshots/` following the existing naming (e.g. `52_triage_queue.png`).

- [ ] **Step 4: Run the full pre-push suite**

Run: `make ci-lint ci-unit` (e2e Playwright via `make ci-e2e` if the environment supports it).
Expected: green.

- [ ] **Step 5: Final commit (screenshot + any doc cross-links)**

```bash
git add docs/screenshots/52_triage_queue.png
git commit -m "docs(triage): add Triage Queue screenshot"
```

---

## Self-Review

**Spec coverage (issue #481 acceptance):**
- Lists scored alerts sorted by `priority_score` desc → Task 1 `triage_view` + Task 2 `data_grid`. ✓
- Per-alert explanation panel → Task 1 `explanation_rows` + Task 2 selectbox + dataframe. ✓
- Advisory framing explicit → Task 2 `st.caption("⚖️ Advisory only…")` + page docstring + tour copy. ✓
- Empty-state (disabled / no alerts) → Task 2 two `st.stop()` branches. ✓
- Audience-routed + `page_header` + footer/sibling guards → Tasks 3 + 5. ✓
- e2e + docs (tour) → Tasks 6 + 4. (README touch only if persona-facing copy changes — not required; tour is the per-page doc surface.) progress.md round entry happens at PR time.

**Placeholder scan:** none — every code step shows complete code; every run step shows the exact command + expected output.

**Type consistency:** `triage.PRIORITY_COL` / `EXPLANATION_COL` / `DISPLAY_COLS` / `has_priority` / `triage_view` / `explanation_rows` / `alert_label` are referenced identically in Task 1 (definitions + tests) and Task 2 (page). `data_grid(...)` kwargs match `dashboard/data_grid.py:99` (`gradient_cols`, `gradient_invert`, `pinned_left`, `drill_*`, `hint`, `height`). `TRIAGE_PAGES` defined in Task 3 step 1 and consumed in step 2/3.

## PR / wrap-up (outside the per-task loop)

- PR body: TODO checklist mirroring issue #481 + `Closes #481` + test plan + screenshot.
- `docs/progress.md`: add the M1 round entry after merge.
- This is dashboard-only (no spec/schema/engine change) → an Azure deploy is warranted (persona-facing UI) per the deploy reflex; bump tag, build, roll both apps, smoke `/Triage_Queue`.
