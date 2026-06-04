# Risk Segmentation + Governed Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Declarative customer-risk segmentation + advisory alert suppression (de-prioritization, never auto-close) layered over the N1 priority score. Closes #495.

**Architecture:** See `docs/superpowers/specs/2026-06-04-risk-segmentation-suppression-design.md`. Optional `program.risk_segmentation` spec block; a pure `engine/suppression.py` that flags eligible alerts; runner integration + a frozen PII-masked `suppression_report.json`; surfaced on dashboard pages 52 + 45. Deterministic, stdlib-only engine path, governed-as-advisory.

**Tech Stack:** Python 3.10+, pydantic v2 (`extra="forbid"`, `frozen=True`), stdlib-only engine; pandas/streamlit on the dashboard.

**Locked decisions:** declarative (no ML clustering in v1); flag-on-alert (no separate ledger event); eligibility = segment match AND `priority_score < deprioritize_below`; precondition = prioritization enabled; advisory/explainable/reversible/deterministic/PII-safe.

---

### Task 1: Spec models + schema sync

**Files:**
- Modify: `src/aml_framework/spec/models.py` (add `RiskSegment`, `RiskSegmentation`; add `risk_segmentation` to `Program`, next to `prioritization`)
- Modify: `schema/aml-spec.schema.json` (regenerate or hand-add the matching block)
- Test: `tests/test_spec_risk_segmentation.py`

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations
import pytest
from pydantic import ValidationError
from aml_framework.spec.models import Program, RiskSegment, RiskSegmentation


def _program(**kw):
    base = dict(name="P", jurisdiction="CA", regulator="FINTRAC", owner="MLRO",
                effective_date="2026-01-01")
    base.update(kw)
    return Program(**base)


def test_program_defaults_risk_segmentation_none():
    assert _program().risk_segmentation is None


def test_valid_risk_segmentation_block():
    seg = RiskSegment(id="low_kyc", values=["low"], deprioritize_below=0.3,
                      rationale="low-risk retail", owner="MLRO")
    rs = RiskSegmentation(enabled=True, segments=[seg])
    p = _program(risk_segmentation=rs)
    assert p.risk_segmentation.enabled is True
    assert p.risk_segmentation.segments[0].field == "customer_risk_rating"  # default
    assert p.risk_segmentation.segments[0].deprioritize_below == 0.3


def test_default_disabled_empty_segments():
    rs = RiskSegmentation()
    assert rs.enabled is False and rs.segments == []


def test_deprioritize_below_must_be_0_1():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=["low"], deprioritize_below=1.5, rationale="r", owner="o")


def test_deprioritize_below_rejects_non_finite():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=["low"], deprioritize_below=float("inf"),
                    rationale="r", owner="o")


def test_values_must_be_non_empty():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=[], deprioritize_below=0.3, rationale="r", owner="o")


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=["low"], deprioritize_below=0.3, rationale="r",
                    owner="o", bogus=1)
```

- [ ] **Step 2: Run, verify fail** — `.venv/bin/python -m pytest tests/test_spec_risk_segmentation.py -q` → ImportError.

- [ ] **Step 3: Implement** — in `src/aml_framework/spec/models.py`, immediately AFTER `ProgramPrioritization` (the class ends ~line 267), add:

```python
class RiskSegment(_Base):
    """One customer-risk segment + its advisory de-prioritization threshold.

    Declarative (the spec is the source of truth): an alert whose customer's
    `field` value is in `values` AND whose advisory `priority_score` is below
    `deprioritize_below` is flagged `suppression.applied=True` — never closed,
    never re-disposed. `rationale`/`owner` are the audit paper-trail.
    """

    id: str = Field(min_length=1)
    field: str = "customer_risk_rating"
    values: list[str] = Field(min_length=1)
    deprioritize_below: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: str = Field(min_length=1)
    owner: str = Field(min_length=1)


class RiskSegmentation(_Base):
    """Advisory risk-segmentation config (governed augmentation).

    When `enabled`, the engine flags low-score alerts in declared low-risk
    segments as de-prioritized (advisory). Off by default; backward-compatible.
    Requires `prioritization` enabled (the score it gates on); when that's
    absent the suppression pass is a no-op with an explicit reason.
    """

    enabled: bool = False
    segments: list[RiskSegment] = Field(default_factory=list)
```

Then in `Program`, after the `prioritization: ProgramPrioritization | None = None` line, add:

```python
    # feat(spec) #495: optional governed risk-segmentation config. See
    # `RiskSegmentation`. When enabled (and prioritization is on), the
    # engine stamps an advisory `suppression` flag on low-score alerts in
    # declared low-risk segments — never alters disposition/queue/state.
    # Default None = segmentation disabled.
    risk_segmentation: RiskSegmentation | None = None
```

- [ ] **Step 4: Sync the JSON schema** — regenerate via the project's schema-gen path if one exists (`grep -rn "model_json_schema\|aml-spec.schema" src/ scripts/`); otherwise hand-add the `RiskSegment`/`RiskSegmentation` definitions + the `risk_segmentation` property on `Program` to `schema/aml-spec.schema.json`, mirroring how `prioritization` appears there. Confirm with the schema-sync test (find it: `grep -rln "aml-spec.schema" tests/`).

- [ ] **Step 5: Run tests + schema test** — `.venv/bin/python -m pytest tests/test_spec_risk_segmentation.py <schema-sync-test> -q` → all PASS.

- [ ] **Step 6: Lint + commit**

```bash
.venv/bin/ruff check src/aml_framework/spec/models.py tests/test_spec_risk_segmentation.py
git add src/aml_framework/spec/models.py schema/aml-spec.schema.json tests/test_spec_risk_segmentation.py
git commit -m "feat(spec): risk_segmentation block — declarative customer segments (#495)"
```

---

### Task 2: Engine — `stamp_suppression` (pure, advisory, deterministic)

**Files:**
- Create: `src/aml_framework/engine/suppression.py`
- Test: `tests/test_suppression.py`

Study `src/aml_framework/engine/prioritization.py` first — mirror its `_Base`/dataclass style, `_coerce_float` robustness, "only ADDS keys, never auto-closes" discipline, and determinism.

- [ ] **Step 1: Write failing tests** (`tests/test_suppression.py`)

```python
from __future__ import annotations
from aml_framework.engine.suppression import SuppressionResult, score_suppression, stamp_suppression
from aml_framework.spec.models import RiskSegment, RiskSegmentation


def _seg(**kw):
    base = dict(id="low_kyc", field="customer_risk_rating", values=["low"],
                deprioritize_below=0.3, rationale="r", owner="o")
    base.update(kw); return RiskSegment(**base)


def _cfg(enabled=True, segments=None):
    return RiskSegmentation(enabled=enabled, segments=segments or [_seg()])


def test_match_and_low_score_is_suppressed():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"})
    assert alert["suppression"]["applied"] is True
    assert alert["suppression"]["segment_id"] == "low_kyc"
    assert alert["suppression"]["reversible"] is True
    assert alert["suppression"]["score"] == 0.1


def test_high_score_not_suppressed_even_in_segment():
    alert = {"customer_id": "C1", "priority_score": 0.9}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"})
    assert alert["suppression"]["applied"] is False


def test_customer_not_in_any_segment_not_suppressed():
    alert = {"customer_id": "C2", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(), {"C2": "high"})
    assert alert["suppression"]["applied"] is False


def test_noop_when_disabled():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(enabled=False), {"C1": "low"})
    assert "suppression" not in alert


def test_noop_when_cfg_none():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], None, {"C1": "low"})
    assert "suppression" not in alert


def test_missing_priority_score_records_precondition_reason():
    alert = {"customer_id": "C1"}  # prioritization disabled → no score
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"})
    assert alert["suppression"]["applied"] is False
    assert "prioritization" in alert["suppression"]["reason"].lower()


def test_never_alters_existing_keys_or_disposition():
    alert = {"customer_id": "C1", "priority_score": 0.1, "disposition": "open", "queue": "L1"}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"})
    assert alert["disposition"] == "open" and alert["queue"] == "L1"


def test_deterministic():
    a1 = {"customer_id": "C1", "priority_score": 0.1}
    a2 = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [a1], _cfg(), {"C1": "low"})
    stamp_suppression(None, [a2], _cfg(), {"C1": "low"})
    assert a1["suppression"] == a2["suppression"]


def test_first_matching_segment_wins_deterministically():
    segs = [_seg(id="s1", deprioritize_below=0.2), _seg(id="s2", deprioritize_below=0.5)]
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(segments=segs), {"C1": "low"})
    assert alert["suppression"]["segment_id"] == "s1"  # first in declared order
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement `src/aml_framework/engine/suppression.py`:**

```python
"""Governed advisory alert suppression — risk-segment de-prioritization (#495).

Post-scoring pass over the alert list. For each declared low-risk segment,
an alert whose customer falls in the segment AND whose advisory
``priority_score`` is below the segment's ``deprioritize_below`` threshold is
flagged ``suppression.applied = True``. This is ADVISORY — it NEVER removes
the alert, changes disposition/queue/open-close state, or deletes keys. The
rule alert still lands in the ledger; suppression is a triage lens an
investigator can override.

Design rules (mirror ``engine/prioritization.py``): pure / deterministic
(no clock, no random, no I/O), stdlib only, only ADDS the ``suppression``
key. Precondition: ``priority_score`` must be present (prioritization
enabled); otherwise the pass records ``applied=False`` with an explicit
reason and suppresses nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SuppressionResult:
    applied: bool
    segment_id: str | None
    reason: str
    threshold: float | None
    score: float | None
    reversible: bool = True


def score_suppression(alert: dict[str, Any], cfg, customer_risk: dict[str, str]) -> SuppressionResult:
    score = alert.get("priority_score")
    if score is None:
        return SuppressionResult(False, None, "prioritization disabled — no priority_score", None, None)
    risk = customer_risk.get(alert.get("customer_id", ""))
    for seg in cfg.segments:
        if risk is not None and risk in seg.values:
            if score < seg.deprioritize_below:
                return SuppressionResult(
                    True, seg.id,
                    f"score {score} < {seg.deprioritize_below} for segment '{seg.id}'",
                    seg.deprioritize_below, score,
                )
            return SuppressionResult(
                False, seg.id, f"score {score} >= {seg.deprioritize_below} for segment '{seg.id}'",
                seg.deprioritize_below, score,
            )
    return SuppressionResult(False, None, "customer not in any declared segment", None, score)


def stamp_suppression(rule, alerts, cfg, customer_risk: dict[str, str]) -> None:
    """Add an advisory ``suppression`` dict to each alert. No-op when cfg is
    None or disabled. Never removes keys, never auto-closes."""
    if cfg is None or not getattr(cfg, "enabled", False):
        return
    for alert in alerts:
        alert["suppression"] = asdict(score_suppression(alert, cfg, customer_risk))
```

- [ ] **Step 4: Run tests → PASS. Step 5: lint. Step 6: commit**

```bash
git add src/aml_framework/engine/suppression.py tests/test_suppression.py
git commit -m "feat(engine): governed advisory suppression over risk segments (#495)"
```

---

### Task 3: Suppression report + runner integration

**Files:**
- Modify: `src/aml_framework/engine/suppression.py` (add `SuppressionReport` + `build_suppression_report`)
- Modify: `src/aml_framework/engine/runner.py` (resolve cfg, build `customer_risk`, call `stamp_suppression` after `stamp_priority`, write `suppression_report.json`, pin hash in manifest)
- Test: `tests/test_suppression_report.py`, extend the runner determinism test

**Context:** In `runner.py`, `stamp_priority(rule, alerts, _prioritization_cfg)` is called at ~lines 1297/1326/1348/1445, and `build_priority_report` + `priority_report.json` write is at ~1523-1550, with `priority_report_hash` pinned in the manifest. Mirror ALL of this for suppression. Build `customer_risk: {customer_id -> risk_rating}` once from the loaded customer table (find how the runner accesses customer rows / the `customer_risk_rating` field; reuse the byod alias resolution if present).

- [ ] **Step 1:** Write `build_suppression_report` mirroring `build_priority_report` (frozen pydantic, `mask_customer_id` callable, counts by segment + by rule, masked top examples, `enabled` flag). Tests assert: disabled→empty report; counts correct; customer_id masked when a masking fn is passed; deterministic `model_dump()`.
- [ ] **Step 2:** Implement; run report tests → PASS.
- [ ] **Step 3:** Wire into `runner.py`: resolve `_segmentation_cfg = getattr(spec.program, "risk_segmentation", None)`; build `customer_risk`; after each `stamp_priority(...)` call add `stamp_suppression(rule, alerts, _segmentation_cfg, customer_risk)`; after the run write `suppression_report.json` and add `suppression_report_hash` to the manifest next to `priority_report_hash`.
- [ ] **Step 4:** Extend the existing run-reproducibility test so two identical runs yield identical `suppression_report.json` + manifest hash. Run `tests/test_prioritization.py`-style determinism + the new tests → PASS.
- [ ] **Step 5:** lint + commit `feat(engine): suppression_report.json + runner integration, manifest-pinned (#495)`.

---

### Task 4: Dashboard surfaces (pages 52 + 45)

**Files:**
- Modify: `src/aml_framework/dashboard/pages/52_Triage_Queue.py` — add a `suppressed` / `segment` column from each alert's `suppression` dict; an "advisory — overridable, never auto-closed" caption; optionally a filter toggle "hide suppressed". Aggregate-only `section_explainer` data_summary (counts, no PII).
- Modify: `src/aml_framework/dashboard/pages/45_FP_Analysis.py` — a "Suppression summary" section reading `suppression_report.json` (count suppressed by segment + by rule).

- [ ] Match the page conventions (no module-level streamlit in importable libs; `section_explainer` aggregate-only; `page_header`/`page_footer`). Parse-check + run `tests/test_section_explainer_migrated_pages.py` + `tests/test_dashboard_page_header.py`. Commit `feat(dashboard): surface advisory suppression on Triage Queue + FP Analysis (#495)`.

---

### Task 5: Docs + example spec

**Files:**
- `docs/spec-reference.md` — document `program.risk_segmentation` (+ each field).
- `docs/how-to/configure-risk-segmentation.md` (new) — task recipe (declare segments → enable prioritization → run → read suppression_report → override on Triage Queue). Must be referenced from README or getting-started or a how-to index (CLI-coverage/how-to test).
- `CLAUDE.md` — Key Design Decision bullet (declarative governed suppression).
- `docs/dashboard-tour.md` — page 52 + 45 sentences (no page-count change).
- `docs/progress.md` — Round entry (#495), dated 2026-06-04.
- One example spec (e.g. `examples/canadian_schedule_i_bank/aml.yaml`) gains an illustrative `risk_segmentation` block (keep determinism — pick thresholds that don't perturb planted-positive expectations; verify `aml validate` + `aml run --seed 42` still pass).

- [ ] Run docs-coverage tests (`tests/test_docs_cli_coverage.py`, `tests/test_dashboard_tour_coverage.py`, `tests/test_docs_links.py`) + `aml validate` on the edited example. Commit `docs(suppression): spec-reference + how-to + CLAUDE/tour/progress + example block (#495)`.

---

### Task 6: Full CI gate

- [ ] `make ci-lint ci-unit ci-coverage` green. `make ci-e2e` green (pages 52 + 45 render the suppression surface). Then final whole-branch review → `superpowers:finishing-a-development-branch` → PR (closes #495) → Codex → CI → merge. Code feature → deploy reflex after main green.

## Self-Review
- Spec coverage: segmentation declared (T1), advisory suppression engine (T2), evidence report + runner + determinism (T3), surfaces (T4), docs+example (T5), gate (T6). ✓
- Determinism: pure stamp; report `model_dump` pinned; manifest hash; example thresholds chosen to not perturb seed-42 positives. ✓
- Governance: advisory-only, never auto-close, explainable, reversible, PII-masked report, prioritization precondition. ✓
- Dependency safety: engine stdlib-only (runs in `.[dev]`); no sklearn. ✓
- Type consistency: `stamp_suppression(rule, alerts, cfg, customer_risk)` + `SuppressionResult`/`SuppressionReport` used identically across engine, runner, dashboard, tests. ✓
