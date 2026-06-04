# Equivalence Divergence Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cluster the NEW_ONLY / LEGACY_ONLY divergences from an `EquivalenceReport` by deterministic "shape signature" so a data scientist triages parallel-run defects by pattern instead of eyeballing thousands of flat rows. Closes #494.

**Architecture:** A new pure-stdlib+pydantic module `engine/equivalence_clustering.py` (mirrors `engine/equivalence.py`: `extra="forbid", frozen=True`, no I/O, no clock, no random state, deterministic). Each NEW_ONLY/LEGACY_ONLY cell gets a canonical signature `(classification, rule_id, severity, window_days)`; same-signature cells form a `DivergenceCluster`. **No statistical ML / sklearn** — that would break the framework's determinism invariant (`test_run_is_reproducible`) and can't run in the `.[dev]`-only unit CI (sklearn/numpy live in `[ml]`, not `[dev]`). Per the roadmap spec, "clusters are explanations; the four-way classification still lands in the ledger" — a deterministic, named shape signature is the most audit-defensible "explanation." The CLI markdown report and dashboard page 48 surface the clusters; the authoritative `EquivalenceReport` is unchanged.

**Tech Stack:** Python 3.10+, pydantic v2 (frozen, extra="forbid"), stdlib only in the engine module; pandas/streamlit in the dashboard page (dashboard group); typer/rich already present for the CLI.

**Design decisions (locked):**
- **Signature = `(classification, rule_id, severity, window_days)`** where for NEW_ONLY `rule_id = rule_id_new` and `severity = new_severity`; for LEGACY_ONLY `rule_id = rule_id_legacy` and `severity = legacy_severity`. `None` rule_id → `"<unmapped>"`; `None` severity → `"unspecified"`. `window_days = (period_end - period_start).days`.
- **Scope = NEW_ONLY and LEGACY_ONLY only.** MATCH and DIFF cells are ignored (MATCH is agreement; DIFF already carries its own `diff_reason`). YAGNI: no payload-field clustering (payload is arbitrary/unstable across specs) — out of scope, note it.
- **Deterministic ordering:** clusters sorted by `size` descending, then by the signature tuple ascending (stringified, stable). Members within a cluster keep `EquivalenceReport.cells` order (already sorted by `(customer, period, rule)`).
- **Governance:** the cluster report is a derived explanation. It does not mutate `EquivalenceReport`, is not hashed into the ledger, and the dashboard/CLI label it as such.

---

### Task 1: Engine — cluster models + `cluster_divergences()`

**Files:**
- Create: `src/aml_framework/engine/equivalence_clustering.py`
- Test: `tests/test_equivalence_clustering.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_equivalence_clustering.py
from __future__ import annotations

from datetime import datetime

from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)
from aml_framework.engine.equivalence_clustering import (
    DivergenceCluster,
    DivergenceClusterReport,
    cluster_divergences,
)

PS = datetime(2026, 1, 1)
PE = datetime(2026, 2, 1)  # 31-day window
GEN = datetime(2026, 6, 4)


def _cell(cust, cls, *, rn=None, rl=None, ns=None, ls=None, ps=PS, pe=PE):
    return EquivalenceCell(
        customer_id=cust,
        period_start=ps,
        period_end=pe,
        rule_id_new=rn,
        rule_id_legacy=rl,
        classification=cls,
        new_severity=ns,
        legacy_severity=ls,
    )


def _report(cells):
    counts = {c: 0 for c in EquivalenceClass}
    for cell in cells:
        counts[cell.classification] += 1
    return EquivalenceReport(cells=cells, counts=counts, by_rule={}, generated_at=GEN)


def test_empty_report_yields_no_clusters():
    report = cluster_divergences(_report([]))
    assert report.clusters == []
    assert report.total_divergences == 0
    assert report.generated_at == GEN


def test_match_and_diff_cells_are_ignored():
    cells = [
        _cell("C1", EquivalenceClass.MATCH, rn="R1", rl="L1"),
        _cell("C2", EquivalenceClass.DIFF, rn="R1", rl="L1", ns="high", ls="medium"),
    ]
    report = cluster_divergences(_report(cells))
    assert report.clusters == []
    assert report.total_divergences == 0


def test_same_shape_new_only_cells_form_one_cluster():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
    ]
    report = cluster_divergences(_report(cells))
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.classification == EquivalenceClass.NEW_ONLY
    assert cluster.rule_id == "STRUCT_CASH"
    assert cluster.severity == "high"
    assert cluster.window_days == 31
    assert cluster.size == 3
    assert [m.customer_id for m in cluster.members] == ["C1", "C2", "C3"]
    assert report.total_divergences == 3


def test_different_shapes_split_into_separate_clusters():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="WIRE_BURST", ns="medium"),
        _cell("C3", EquivalenceClass.LEGACY_ONLY, rl="STRUCT_CASH", ls="high"),
    ]
    report = cluster_divergences(_report(cells))
    assert len(report.clusters) == 3


def test_legacy_only_uses_legacy_rule_and_severity():
    cells = [_cell("C1", EquivalenceClass.LEGACY_ONLY, rl="DORMANT", ls="low")]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert cluster.classification == EquivalenceClass.LEGACY_ONLY
    assert cluster.rule_id == "DORMANT"
    assert cluster.severity == "low"


def test_none_rule_and_severity_use_sentinels():
    cells = [_cell("C1", EquivalenceClass.NEW_ONLY, rn=None, ns=None)]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert cluster.rule_id == "<unmapped>"
    assert cluster.severity == "unspecified"


def test_label_is_human_readable():
    cells = [_cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high")]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    # e.g. "NEW_ONLY · STRUCT_CASH · high severity · 31-day window (1)"
    assert "NEW_ONLY" in cluster.label
    assert "STRUCT_CASH" in cluster.label
    assert "high" in cluster.label
    assert "31" in cluster.label


def test_clusters_sorted_by_size_desc_then_signature():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
    ]
    clusters = cluster_divergences(_report(cells)).clusters
    assert clusters[0].rule_id == "B" and clusters[0].size == 2  # bigger first
    assert clusters[1].rule_id == "A" and clusters[1].size == 1


def test_deterministic_same_input_same_output():
    cells = [
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C1", EquivalenceClass.LEGACY_ONLY, rl="B", ls="low"),
    ]
    r1 = cluster_divergences(_report(cells))
    r2 = cluster_divergences(_report(cells))
    assert r1.model_dump() == r2.model_dump()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_equivalence_clustering.py -q`
Expected: FAIL (ModuleNotFoundError: equivalence_clustering)

- [ ] **Step 3: Implement the module**

```python
# src/aml_framework/engine/equivalence_clustering.py
"""Deterministic shape-signature clustering of equivalence divergences (#494).

Post-hoc analyzer over ``EquivalenceReport``. Groups the NEW_ONLY and
LEGACY_ONLY cells — the cells where the two systems *disagree* — by a
canonical "shape signature" so a data scientist triages parallel-run
defects by pattern (e.g. "47 NEW_ONLY on STRUCT_CASH, high severity,
31-day window") instead of scrolling thousands of flat rows.

Design rules (mirror ``engine/equivalence.py``):

* **Pure / deterministic.** No I/O, no clock reads, no random state.
  Same ``EquivalenceReport`` → identical ``DivergenceClusterReport``.
  This is why clustering is a fixed shape signature, *not* k-means or
  any sklearn estimator: the framework's determinism contract
  (``test_run_is_reproducible``) and the ``.[dev]``-only unit CI (no
  sklearn/numpy) both forbid stochastic clustering here.
* **Stdlib + pydantic only.** No pandas, no sklearn, no new deps.
* **Explanation, not record.** The cluster report does not mutate the
  ``EquivalenceReport`` and is not hashed into the ledger. The four-way
  classification remains authoritative; clusters are a triage lens.

Signature = ``(classification, rule_id, severity, window_days)`` where
for NEW_ONLY the rule/severity come from the *new* side and for
LEGACY_ONLY from the *legacy* side. MATCH and DIFF cells are out of
scope (agreement / already-explained-by-diff_reason).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)

_UNMAPPED_RULE = "<unmapped>"
_UNSPECIFIED_SEVERITY = "unspecified"

# Only these two classes are "divergences" worth clustering.
_DIVERGENCE_CLASSES = (EquivalenceClass.NEW_ONLY, EquivalenceClass.LEGACY_ONLY)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DivergenceMember(_Base):
    """One divergent cell's identity inside a cluster (for drill-down)."""

    customer_id: str
    period_start: datetime
    period_end: datetime
    rule_id_new: str | None = None
    rule_id_legacy: str | None = None


class DivergenceCluster(_Base):
    """A group of divergent cells sharing one shape signature."""

    classification: EquivalenceClass
    rule_id: str
    severity: str
    window_days: int
    label: str
    size: int
    members: list[DivergenceMember]


class DivergenceClusterReport(_Base):
    """Shape-signature clustering of an ``EquivalenceReport``'s divergences."""

    clusters: list[DivergenceCluster]
    total_divergences: int
    generated_at: datetime


def _signature(cell: EquivalenceCell) -> tuple[EquivalenceClass, str, str, int]:
    if cell.classification is EquivalenceClass.NEW_ONLY:
        rule_id = cell.rule_id_new or _UNMAPPED_RULE
        severity = cell.new_severity or _UNSPECIFIED_SEVERITY
    else:  # LEGACY_ONLY
        rule_id = cell.rule_id_legacy or _UNMAPPED_RULE
        severity = cell.legacy_severity or _UNSPECIFIED_SEVERITY
    window_days = (cell.period_end - cell.period_start).days
    return (cell.classification, rule_id, severity, window_days)


def _label(sig: tuple[EquivalenceClass, str, str, int], size: int) -> str:
    classification, rule_id, severity, window_days = sig
    return (
        f"{classification.value} · {rule_id} · {severity} severity · "
        f"{window_days}-day window ({size})"
    )


def cluster_divergences(report: EquivalenceReport) -> DivergenceClusterReport:
    """Cluster NEW_ONLY/LEGACY_ONLY cells by deterministic shape signature.

    Returns a ``DivergenceClusterReport`` whose clusters are sorted by
    ``size`` descending, then by the signature ascending (stable). Member
    cells keep their original ``report.cells`` order.
    """
    # Preserve first-seen signature → members order; report.cells is
    # already sorted deterministically by the classifier.
    grouped: dict[tuple[EquivalenceClass, str, str, int], list[DivergenceMember]] = {}
    for cell in report.cells:
        if cell.classification not in _DIVERGENCE_CLASSES:
            continue
        sig = _signature(cell)
        grouped.setdefault(sig, []).append(
            DivergenceMember(
                customer_id=cell.customer_id,
                period_start=cell.period_start,
                period_end=cell.period_end,
                rule_id_new=cell.rule_id_new,
                rule_id_legacy=cell.rule_id_legacy,
            )
        )

    clusters = [
        DivergenceCluster(
            classification=sig[0],
            rule_id=sig[1],
            severity=sig[2],
            window_days=sig[3],
            label=_label(sig, len(members)),
            size=len(members),
            members=members,
        )
        for sig, members in grouped.items()
    ]
    # Deterministic: size desc, then signature ascending (stringified for
    # a total order across the mixed-type tuple).
    clusters.sort(key=lambda c: (-c.size, str(_signature_of(c))))

    total = sum(c.size for c in clusters)
    return DivergenceClusterReport(
        clusters=clusters, total_divergences=total, generated_at=report.generated_at
    )


def _signature_of(cluster: DivergenceCluster) -> tuple[str, str, str, int]:
    return (
        cluster.classification.value,
        cluster.rule_id,
        cluster.severity,
        cluster.window_days,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_equivalence_clustering.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Lint**

Run: `ruff check src/aml_framework/engine/equivalence_clustering.py tests/test_equivalence_clustering.py && ruff format --check src/aml_framework/engine/equivalence_clustering.py tests/test_equivalence_clustering.py`
Expected: clean (run `ruff format` if needed)

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/engine/equivalence_clustering.py tests/test_equivalence_clustering.py
git commit -m "feat(equivalence): deterministic shape-signature divergence clustering (#494)"
```

---

### Task 2: CLI — render a "Divergence clusters" section in the equivalence markdown

**Files:**
- Modify: `src/aml_framework/cli.py` (function `_render_equivalence_markdown`, ends ~line 2846 with `return "\n".join(lines)`)
- Test: `tests/test_cli_equivalence_clusters.py` (new) — test the renderer's cluster section directly

**Context:** `_render_equivalence_markdown(report, *, run_dir, legacy_path)` builds the markdown evidence snippet (Counts table, By-rule table, then "first 20 of N" per class). Add a "## Divergence clusters" section AFTER the By-rule table and BEFORE the per-class cell tables, listing the clusters as a table. Keep the deterministic-explanation framing in a one-line caption.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_equivalence_clusters.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aml_framework.cli import _render_equivalence_markdown
from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)

GEN = datetime(2026, 6, 4)


def _report(cells):
    counts = {c: 0 for c in EquivalenceClass}
    for cell in cells:
        counts[cell.classification] += 1
    return EquivalenceReport(cells=cells, counts=counts, by_rule={}, generated_at=GEN)


def _new_only(cust, rule, sev):
    return EquivalenceCell(
        customer_id=cust,
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 2, 1),
        rule_id_new=rule,
        rule_id_legacy=None,
        classification=EquivalenceClass.NEW_ONLY,
        new_severity=sev,
    )


def test_markdown_has_divergence_clusters_section():
    report = _report([_new_only("C1", "STRUCT_CASH", "high"), _new_only("C2", "STRUCT_CASH", "high")])
    md = _render_equivalence_markdown(report, run_dir=Path("/tmp/run-x"), legacy_path=Path("/tmp/legacy.csv"))
    assert "## Divergence clusters" in md
    assert "STRUCT_CASH" in md
    # the cluster of 2 should report size 2
    assert "| 2 |" in md or "| 2 " in md


def test_markdown_clusters_section_empty_when_no_divergences():
    md = _render_equivalence_markdown(_report([]), run_dir=Path("/tmp/r"), legacy_path=Path("/tmp/l.csv"))
    assert "## Divergence clusters" in md
    assert "_No divergences to cluster._" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_equivalence_clusters.py -q`
Expected: FAIL (no "## Divergence clusters" in output)

- [ ] **Step 3: Implement — insert the cluster section into `_render_equivalence_markdown`**

Find the block right after the By-rule table (the `lines.append("")` that follows the `else: lines.append("_No rules classified._")` block, immediately before the `# Top 20 of each class` comment). Insert:

```python
    # Divergence clusters (NEW_ONLY / LEGACY_ONLY grouped by shape).
    # A triage lens — the four-way classification above is authoritative.
    from aml_framework.engine.equivalence_clustering import cluster_divergences

    cluster_report = cluster_divergences(report)
    lines.append("## Divergence clusters")
    lines.append("")
    lines.append(
        "_Shape-signature grouping of NEW_ONLY / LEGACY_ONLY cells "
        "(a triage lens; the four-way classification above is authoritative)._"
    )
    lines.append("")
    if cluster_report.clusters:
        lines.append("| Classification | Rule | Severity | Window (days) | Size |")
        lines.append("| --- | --- | --- | ---: | ---: |")
        for cl in cluster_report.clusters:
            lines.append(
                f"| {cl.classification.value} | `{cl.rule_id}` | {cl.severity} | "
                f"{cl.window_days} | {cl.size} |"
            )
    else:
        lines.append("_No divergences to cluster._")
    lines.append("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli_equivalence_clusters.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Regression — existing CLI/equivalence tests still pass**

Run: `python -m pytest tests/test_engine_equivalence.py tests/test_cli_equivalence_clusters.py tests/test_equivalence_clustering.py -q`
Expected: all PASS

- [ ] **Step 6: Lint + commit**

```bash
ruff check src/aml_framework/cli.py tests/test_cli_equivalence_clusters.py
ruff format --check src/aml_framework/cli.py tests/test_cli_equivalence_clusters.py
git add src/aml_framework/cli.py tests/test_cli_equivalence_clusters.py
git commit -m "feat(equivalence): surface divergence clusters in the CLI markdown report (#494)"
```

---

### Task 3: Dashboard — "Divergence clusters" section on page 48

**Files:**
- Modify: `src/aml_framework/dashboard/pages/48_Equivalence.py` (insert AFTER the cell-level classification table block ~line 484, BEFORE the "Related Links" block ~line 492)

**Context:** Page 48 already loads the report into `report` and uses `pd`, `st`, `page_header`, `section_explainer`. The cell table is capped at 200 rows. Add a clusters section: a `st.dataframe` of clusters + a `st.expander`/`st.selectbox` drill-down into one cluster's members. This is a Streamlit page — keep it self-contained (lazy imports only; no `streamlit` at module level beyond the existing pattern in the file). Match the existing components and the governance caption.

- [ ] **Step 1: Read the existing cell-table block to match style**

Read `src/aml_framework/dashboard/pages/48_Equivalence.py` lines 449–500. Note how `report.cells` is turned into a DataFrame and how the "Related Links" block begins (the insertion boundary).

- [ ] **Step 2: Insert the clusters section**

Immediately after the cell-table block (after its truncation `st.caption(...)` / before the related-links markdown), insert:

```python
    # ---- Divergence clusters (shape-signature triage lens) ----
    from aml_framework.engine.equivalence_clustering import cluster_divergences

    st.subheader("Divergence clusters")
    section_explainer(
        "Shape-signature grouping of the NEW_ONLY / LEGACY_ONLY cells — "
        "same rule, severity, and window length cluster together so you "
        "triage defects by pattern. This is a triage lens; the four-way "
        "classification above is what lands in the ledger.",
    )
    cluster_report = cluster_divergences(report)
    if not cluster_report.clusters:
        st.info("No NEW_ONLY / LEGACY_ONLY divergences to cluster — the runs agree.")
    else:
        clusters_df = pd.DataFrame(
            [
                {
                    "classification": cl.classification.value,
                    "rule": cl.rule_id,
                    "severity": cl.severity,
                    "window_days": cl.window_days,
                    "size": cl.size,
                }
                for cl in cluster_report.clusters
            ]
        )
        st.dataframe(clusters_df, use_container_width=True, hide_index=True)
        st.caption(
            f"{len(cluster_report.clusters)} cluster(s) over "
            f"{cluster_report.total_divergences} divergent cell(s)."
        )
        labels = [cl.label for cl in cluster_report.clusters]
        chosen = st.selectbox("Drill into a cluster", labels, key="equiv_cluster_pick")
        picked = cluster_report.clusters[labels.index(chosen)]
        members_df = pd.DataFrame(
            [
                {
                    "customer_id": m.customer_id,
                    "period_start": m.period_start.isoformat(),
                    "period_end": m.period_end.isoformat(),
                    "rule_id_new": m.rule_id_new or "",
                    "rule_id_legacy": m.rule_id_legacy or "",
                }
                for m in picked.members
            ]
        )
        st.dataframe(members_df, use_container_width=True, hide_index=True)
```

- [ ] **Step 3: Convention test — page still passes the dashboard convention suite**

Run: `python -m pytest tests/test_dashboard_pages_conventions.py -q` (or the file that enforces `page_header`/`section_explainer`; find it with `grep -rl section_explainer tests/`)
Expected: PASS. If the convention test imports the page module, confirm there's no module-level `streamlit` import added.

- [ ] **Step 4: Smoke — page imports without a running Streamlit context**

Run: `python -c "import ast; ast.parse(open('src/aml_framework/dashboard/pages/48_Equivalence.py').read()); print('ok')"`
Expected: `ok` (syntactic check; full render is covered by e2e in Task 5/CI)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/aml_framework/dashboard/pages/48_Equivalence.py
ruff format --check src/aml_framework/dashboard/pages/48_Equivalence.py
git add src/aml_framework/dashboard/pages/48_Equivalence.py
git commit -m "feat(equivalence): divergence clusters section + drill-down on page 48 (#494)"
```

---

### Task 4: Docs

**Files:**
- Modify: `CLAUDE.md` (Architecture / Key Design Decisions area)
- Modify: `docs/dashboard-tour.md` (the Equivalence page entry)
- Modify: `docs/how-to/triage-defects.md` (add the clustering step — this is the defect-triage workflow recipe)
- Modify: `docs/progress.md` (Round entry)

- [ ] **Step 1: CLAUDE.md** — add one bullet under "Key Design Decisions" (after the equivalence/point-in-time entries) describing deterministic shape-signature divergence clustering:

```markdown
- **Equivalence divergence clustering (#494):** `engine/equivalence_clustering.py` groups an `EquivalenceReport`'s NEW_ONLY/LEGACY_ONLY cells by a deterministic shape signature `(classification, rule_id, severity, window_days)` — a triage lens, pure stdlib+pydantic, no sklearn (determinism + `.[dev]`-only unit CI forbid stochastic clustering). The four-way classification stays authoritative in the ledger; clusters are explanations surfaced in the `aml equivalence` markdown and on dashboard page 48.
```

- [ ] **Step 2: docs/dashboard-tour.md** — in the Equivalence page paragraph, add a sentence: "A **Divergence clusters** section groups NEW_ONLY/LEGACY_ONLY cells by shape (rule + severity + window) with a per-cluster drill-down, so a DS triages defects by pattern." (Keep the existing screenshot embed/structure; do not change the page count.)

- [ ] **Step 3: docs/how-to/triage-defects.md** — add a step showing the clusters output: run `aml equivalence ... --markdown report.md`, then read the "## Divergence clusters" table to pick the largest shape first; note it's a triage lens, the four-way table is authoritative. Match the file's existing step format.

- [ ] **Step 4: docs/progress.md** — add a Round entry (top of the rounds list, matching the existing format) recording: "#494 Equivalence divergence clustering — deterministic shape-signature grouping (engine + CLI markdown + page 48 drill-down); Next-tier ML/AI roadmap item, governed-as-explanation."

- [ ] **Step 5: Docs-coverage tests**

Run: `python -m pytest tests/test_dashboard_tour_coverage.py tests/test_docs_cli_coverage.py tests/test_docs_links.py -q`
Expected: PASS (the `aml equivalence` command already exists in docs, so no new-command coverage gap; if `test_docs_cli_coverage` flags anything, ensure the recipe references the existing command name).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/dashboard-tour.md docs/how-to/triage-defects.md docs/progress.md
git commit -m "docs(equivalence): document divergence clustering across CLAUDE/tour/how-to/progress (#494)"
```

---

### Task 5: Full local CI gate

**Files:** none (verification only)

- [ ] **Step 1: Run the unit + lint + coverage gate**

Run: `make ci-lint ci-unit ci-coverage`
Expected: green. The new engine module is pure-stdlib so it runs in `.[dev]`; the dashboard change is covered by convention tests + e2e.

- [ ] **Step 2: Run the dashboard e2e if touched (page 48)**

Run: `make ci-e2e` (Playwright, ~15 min) — confirm page 48 renders the clusters section without error. If the e2e suite has an equivalence-page test, assert the "Divergence clusters" subheader is visible.

- [ ] **Step 3: Final** — proceed to the final whole-branch review (subagent-driven-development) then `superpowers:finishing-a-development-branch` to open the PR (closes #494). This is a code feature → after merge, follow the deploy reflex (tag bump + Azure roll) per the release memories.

---

## Self-Review

- **Spec coverage:** #494 asks for shape-clustering of NEW_ONLY/LEGACY_ONLY divergences for fast DS triage — Task 1 (engine) + Task 2 (CLI) + Task 3 (dashboard) cover the surface; Task 4 documents it. ✓
- **Determinism:** signature is a fixed tuple; sort key is total-ordered via stringified signature; tests pin determinism. ✓
- **Dependency safety:** engine module is stdlib+pydantic (runs in `.[dev]` unit CI); no sklearn/numpy/pandas in the engine or its tests. Dashboard uses pandas (dashboard group only). ✓
- **Governance:** cluster report never mutates `EquivalenceReport` and is labeled a triage lens in CLI + dashboard. ✓
- **Type consistency:** `cluster_divergences(report: EquivalenceReport) -> DivergenceClusterReport`; `DivergenceCluster`/`DivergenceMember` used identically across engine, CLI, dashboard, and tests. ✓
- **No placeholders:** every step has full code. ✓
