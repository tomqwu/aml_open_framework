# Model-Risk Monitoring Automation — Implementation Plan (#497)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Fresh implementer per task + two-stage review. Steps use `- [ ]`.

**Goal:** Emit a governed, frozen, manifest-pinned `model_risk_report.json` per run that rolls the model inventory + per-rule drift (count-based, vs prior run) + validation-cadence status into one SR 11-7 / OSFI E-23 model-risk monitoring artifact, surfaced on the dashboard. Closes #497.

**Architecture:** MVP reuses what exists — `generators/model_inventory.py` (the registry), `engine/monitoring_digest.py` (already computes per-rule `changed_since_last_run` deltas vs the prior run), and the count-based drift heuristic already on page 50. A new pure builder `engine/model_risk_monitoring.py` combines them into a `ModelRiskReport`; the runner writes + pins it (mirroring `priority_outcome.json` / `suppression_report.json`); an optional `program.model_risk_monitoring` spec block gates it (off by default → disabled path byte-identical). No PSI/KS statistical drift (deferred — needs per-alert feature vectors the payload doesn't carry); MVP is count-based + cadence, deterministic given the run + its prior-run digest context.

**Tech Stack:** Python 3.10+, pydantic v2 (frozen, extra="forbid"), stdlib engine; pandas/streamlit dashboard.

**Locked decisions:** advisory (a monitoring lens — never blocks a run or auto-changes a model); deterministic given inputs (no clock — `as_of` from the ledger); off by default; reuses inventory + digest (no new prior-run DB plumbing in the engine path); count-based drift only (MVP).

---

### Task 1: Spec block `program.model_risk_monitoring`

**Files:** Modify `src/aml_framework/spec/models.py` (+ `RiskSegmentation` pattern), `schema/aml-spec.schema.json`; Test `tests/test_spec_model_risk_monitoring.py`.

- [ ] Write failing tests (mirror tests/test_spec_risk_segmentation.py): defaults None on Program; valid block; `drift_high_ratio` ≥ 1.0 and finite; `baseline_runs` ≥ 1; extra forbidden.
- [ ] Add to models.py after `RiskSegmentation`:
```python
class ModelRiskMonitoring(_Base):
    """Governed model-risk monitoring config (SR 11-7 / OSFI E-23).

    When `enabled`, the engine emits a frozen, manifest-pinned
    `model_risk_report.json` rolling the model inventory + per-rule
    count-based drift (vs the prior run) + validation-cadence status.
    Advisory/monitoring only — never blocks a run or changes a model.
    Off by default; backward-compatible.
    """

    enabled: bool = False
    drift_high_ratio: float = Field(default=2.0, ge=1.0, allow_inf_nan=False)
    baseline_runs: int = Field(default=10, ge=1)
```
Add `model_risk_monitoring: ModelRiskMonitoring | None = None` to `Program` after `risk_segmentation`. Sync the JSON schema (mirror the `risk_segmentation` $ref + $defs block: properties enabled/drift_high_ratio(number,min 1)/baseline_runs(integer,min 1), additionalProperties:false).
- [ ] Run the new tests + `pytest -k "spec or schema or loader or validate"` green. Lint. Commit `feat(spec): model_risk_monitoring block (#497)`.

---

### Task 2: Engine — `build_model_risk_report`

**Files:** Create `src/aml_framework/engine/model_risk_monitoring.py`; Test `tests/test_model_risk_monitoring.py`.

**Inputs (all already available in the runner):** the model inventory dict (`build_model_inventory(spec)`), the current run's per-rule alert counts (`alerts_per_rule`), and the prior-run per-rule counts the monitoring digest already resolves (`changed_since_last_run` gives current+prior). The builder is pure: no I/O, no clock.

- [ ] Write failing tests: empty/no-prior → all models `drift="unknown"`/`"normal"`, no crash; a rule whose current count ≥ `drift_high_ratio` × prior (or ≤ 1/ratio ×) → `drift="high"`; deterministic `model_dump()`; cadence status derived; disabled handled by the runner (builder always builds when called).
- [ ] Implement:
```python
"""Governed model-risk monitoring report (#497).

Pure builder: rolls the model inventory + per-rule count drift (vs the
prior run) + validation cadence into a frozen ModelRiskReport. Advisory
— a monitoring lens, never blocks a run or mutates a model. Deterministic
(no clock/IO); `generated_at` is supplied by the caller.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelRiskEntry(_Base):
    model_key: str
    kind: str
    tier: str
    owner: str
    current_alerts: int
    prior_alerts: int | None
    drift: str          # "high" | "normal" | "unknown"
    drift_ratio: float | None
    cadence_months: int | None


class ModelRiskReport(_Base):
    enabled: bool
    n_models: int
    n_high_drift: int
    entries: list[ModelRiskEntry]
    generated_at: datetime


def build_model_risk_report(
    inventory: dict[str, Any],
    *,
    current_counts: dict[str, int],
    prior_counts: dict[str, int] | None,
    drift_high_ratio: float,
    generated_at: datetime,
) -> ModelRiskReport:
    entries: list[ModelRiskEntry] = []
    for m in inventory.get("models", []):
        key = m["model_key"]
        cur = int(current_counts.get(key, 0))
        prior = None if prior_counts is None else int(prior_counts.get(key, 0))
        drift, ratio = _drift(cur, prior, drift_high_ratio)
        entries.append(ModelRiskEntry(
            model_key=key, kind=m.get("kind", ""), tier=m.get("tier", ""),
            owner=m.get("owner", ""), current_alerts=cur, prior_alerts=prior,
            drift=drift, drift_ratio=ratio, cadence_months=m.get("cadence_months"),
        ))
    entries.sort(key=lambda e: (e.drift != "high", e.tier, e.model_key))  # high first, deterministic
    return ModelRiskReport(
        enabled=True, n_models=len(entries),
        n_high_drift=sum(1 for e in entries if e.drift == "high"),
        entries=entries, generated_at=generated_at,
    )


def _drift(cur: int, prior: int | None, ratio: float) -> tuple[str, float | None]:
    if prior is None:
        return "unknown", None
    if prior == 0:
        return ("high", None) if cur > 0 else ("normal", 1.0)
    r = cur / prior
    if r >= ratio or r <= 1.0 / ratio:
        return "high", round(r, 3)
    return "normal", round(r, 3)
```
- [ ] Tests green, lint, commit `feat(engine): model_risk_report builder — count drift + cadence (#497)`.

---

### Task 3: Runner integration + manifest pin

**Files:** Modify `src/aml_framework/engine/runner.py`, `src/aml_framework/engine/audit.py`; extend the reproducibility test.

- [ ] Resolve `_mrm_cfg = getattr(spec.program, "model_risk_monitoring", None)` near the other config resolves. Where the monitoring_digest is built (it already has current + prior per-rule counts), and `if _mrm_cfg and _mrm_cfg.enabled`: call `build_model_inventory(spec)`, pull current/prior per-rule counts from the same source the digest uses, call `build_model_risk_report(...)` with `generated_at=ledger.as_of`, write `model_risk_report.json`, and let finalize pin `model_risk_report_hash` (mirror priority_outcome). Add `"model_risk_report.json"` to `_FROZEN_SNAPSHOT_TARGETS` in audit.py and the conditional hash add (only when the file exists → disabled path byte-identical).
- [ ] Determinism test: two seed-42 runs with `model_risk_monitoring.enabled=True` → identical `model_risk_report.json` + identical `model_risk_report_hash`; a run WITHOUT the block → no file, no manifest key (byte-identical to before). Existing `test_run_is_reproducible` still passes.
- [ ] Tests green, lint, commit `feat(engine): emit model_risk_report.json, manifest-pinned (#497)`.

---

### Task 4: Dashboard — surface on Drift Monitor (page 50)

**Files:** Modify `src/aml_framework/dashboard/pages/50_Drift_Monitor.py`.

- [ ] Add a "Model-risk report" section: when `model_risk_report.json` exists in the run dir, render the entries as a table (model_key/kind/tier/owner/current/prior/drift/ratio/cadence) with high-drift rows surfaced first; a one-line governance caption ("Advisory monitoring — never blocks a run or changes a model"). Aggregate-only `section_explainer` data_summary (n_models, n_high_drift). Graceful when absent/disabled (the common case): a one-line "Model-risk monitoring not enabled" note. Page-level explainer stays `collapsed=True` (matches the mobile-polish convention). No module-level streamlit in importable libs.
- [ ] Convention tests (`test_section_explainer_migrated_pages.py`, `test_dashboard_page_header.py`) green. Parse-check. Lint. Commit `feat(dashboard): surface model-risk report on Drift Monitor (#497)`.

---

### Task 5: Docs + example

**Files:** `docs/spec-reference.md`, `docs/how-to/` (new `monitor-model-risk.md`, indexed), `CLAUDE.md`, `docs/dashboard-tour.md`, `docs/progress.md`; enable the block in one example.

- [ ] spec-reference: document `program.model_risk_monitoring`. CLAUDE.md: Key Design Decision bullet. dashboard-tour: page 50 sentence (no count change). progress.md: #497 entry (2026-06-05). how-to: a recipe (enable → run → read model_risk_report.json + Drift Monitor). Enable the block on one example; verify `aml validate` + determinism tests still pass (the report is additive; confirm no golden break — if a golden pins the example manifest, regenerate or keep enabled=true only if clean).
- [ ] Docs-coverage tests green. Commit `docs(model-risk): spec-reference + how-to + CLAUDE/tour/progress + example (#497)`.

---

### Task 6: Full CI gate

- [ ] `make ci-lint ci-unit ci-coverage` green; `make ci-e2e` green (page 50 renders the report). Final whole-branch review → finishing-a-development-branch → PR (closes #497) → Codex → CI → merge → deploy reflex.

## Self-Review
- Spec ✓ (T1), engine builder ✓ (T2), runner+pin+determinism ✓ (T3), dashboard ✓ (T4), docs+example ✓ (T5), gate ✓ (T6).
- Determinism: pure builder, `generated_at` from ledger, disabled-path byte-identical (conditional pin), sorted entries.
- Governance: advisory/monitoring only, never blocks/mutates; evidenced (frozen + pinned); off by default.
- Dependency safety: engine stdlib+pydantic; reuses inventory + digest; no PSI/KS/sklearn.
- Type consistency: `build_model_risk_report(...)` + `ModelRiskReport`/`ModelRiskEntry` used identically across engine, runner, dashboard, tests.
