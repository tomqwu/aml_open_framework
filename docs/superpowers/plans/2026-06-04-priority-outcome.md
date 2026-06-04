# M3 — Champion-Challenger Priority Outcome + Temporal-Leakage Guard (N1 follow-on) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic champion-vs-challenger backtest of the N1 prioritization scorer that scores historical **labelled** alerts, computes precision@k + recall per config, writes a frozen+manifest-pinned `priority_outcome.json`, and a temporal-leakage guard proving the scorer uses only as-of features.

**Architecture:** A pure `engine/priority_outcome.py` builds the outcome from a run's alerts + a label map + champion/challenger configs (reusing `engine/prioritization.score_alert`). The runner writes `priority_outcome.json` during finalize when `aml run --labels` is supplied (mirroring `priority_report.json`); `engine/audit.py` pins `priority_outcome_hash` and freezes the file. A feature-allowlist constant + regression test enforce no-leakage.

**Tech Stack:** Python 3.10+, Pydantic v2 (frozen models), Typer, pytest.

---

## Background facts (verified)

- `engine/prioritization.py`: `score_alert(alert, rule, config) -> PriorityResult(score, explanation)` (line 83). It is **stateless per-alert** — reads only `alert["sum_amount"]`/`["amount"]`, `alert["count"]`/`len(matched_row_ids)`, and `rule.severity`/`rule.risk_tier`. No `datetime.now()`, no global/time lookups → no temporal leakage is possible in the weighted scorer today. `config` is a `ProgramPrioritization` (`.enabled`, `.weights`).
- Labels: `engine/backtest.py` uses `labels_loader(period) -> {customer_id: bool}`; `aml backtest --labels CSV` (cli.py:2929) parses `customer_id,is_true_positive`. Synthetic planted positives are customers `C0001`–`C0029` (+ replica `C0030`–`C0059`); no `label` field on alerts — truth is keyed by `customer_id`.
- `priority_report.json` freeze/pin pattern to mirror: runner `_write_priority_report(run_dir, report)` (runner.py:933), called when `_prioritization_cfg and .enabled` (runner.py:1505); audit pins `priority_report_hash` (audit.py:536-544, manifest key line 592) and freezes via `_FROZEN_SNAPSHOT_BASENAMES` (audit.py:226). Determinism test: `test_priority_report_is_manifest_pinned_and_frozen` (test_prioritization.py:166).
- Run `as_of`: the runner stamps `window_end = as_of` on every alert; `aml run` accepts `--as-of`. Determinism contract: same spec+data+seed+as_of = byte-identical.
- Precision/recall helpers exist in `engine/tuning.py` (`_precision`, `_recall`) but operate on a predicted SET; **precision@k needs ranking**, so M3 implements `precision_at_k`/`recall` over the score-ranked list directly (small, pure).

## File Structure

- **Create** `src/aml_framework/engine/priority_outcome.py` — `LEAKAGE_SAFE_FEATURES`, `score_for_config`, `precision_at_k`, `recall_at_labels`, `build_priority_outcome(...)`, `PriorityOutcome` model.
- **Create** `tests/test_priority_outcome.py` — generator + leakage-guard tests.
- **Modify** `src/aml_framework/engine/runner.py` — write `priority_outcome.json` during finalize when labels supplied; thread `--labels`/`--challenger-weights`.
- **Modify** `src/aml_framework/engine/audit.py` — pin `priority_outcome_hash` + add to frozen basenames.
- **Modify** `src/aml_framework/cli.py` — `aml run` gains `--labels` / `--challenger-weights`; OR a standalone `aml priority-outcome` reading a run dir (this plan wires `aml run` for the pin/freeze, and reuses the same builder).
- **Modify** `README.md` + `docs/progress.md`.

## Outcome contract

`PriorityOutcome` (frozen):
```
enabled: bool
n_alerts: int
n_labelled_positives: int
k_values: list[int]                # e.g. [5, 10, 20]
champion: ConfigOutcome
challenger: ConfigOutcome
winner: str                        # "champion" | "challenger" | "tie" (by recall, then p@max-k)
```
`ConfigOutcome`: `precision_at_k: dict[str,float]`, `recall: float`, `mean_score: float`, `weights: dict[str,float]`.
Deterministic: rounded to 6 dp, sorted keys, no wall-clock.

---

### Task 1: pure outcome builder + leakage allowlist

**Files:**
- Create: `src/aml_framework/engine/priority_outcome.py`
- Test: `tests/test_priority_outcome.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_priority_outcome.py
from __future__ import annotations

from types import SimpleNamespace

from aml_framework.engine.priority_outcome import (
    LEAKAGE_SAFE_FEATURES,
    build_priority_outcome,
    precision_at_k,
    recall_at_labels,
)
from aml_framework.spec.models import ProgramPrioritization


def _rule(rid="r1", severity="high", risk_tier=None):
    return SimpleNamespace(id=rid, severity=severity, risk_tier=risk_tier)


def _alert(cid, amount, count):
    return {"customer_id": cid, "rule_id": "r1", "sum_amount": amount, "count": count}


def test_precision_at_k_counts_true_positives_in_top_k():
    # ranked customer ids (desc by score) + label map
    ranked = ["C0001", "C9999", "C0002", "C8888"]
    labels = {"C0001": True, "C0002": True}
    assert precision_at_k(ranked, labels, 2) == 0.5  # C0001 true, C9999 false
    assert precision_at_k(ranked, labels, 4) == 0.5  # 2 true of 4


def test_recall_counts_labelled_positives_surfaced():
    ranked = ["C0001", "C9999"]
    labels = {"C0001": True, "C0002": True}  # 2 positives, only C0001 surfaced
    assert recall_at_labels(ranked, labels) == 0.5


def test_build_outcome_champion_vs_challenger_deterministic():
    rule = _rule()
    alerts_by_rule = {
        "r1": [_alert("C0001", 90000, 9), _alert("C9999", 100, 1), _alert("C0002", 50000, 5)]
    }
    labels = {"C0001": True, "C0002": True, "C9999": False}
    champ = ProgramPrioritization(enabled=True)
    chall = ProgramPrioritization(enabled=True, weights={"amount": 5.0})
    rules = {"r1": rule}
    out_a = build_priority_outcome(alerts_by_rule, rules, labels, champion=champ, challenger=chall)
    out_b = build_priority_outcome(alerts_by_rule, rules, labels, champion=champ, challenger=chall)
    assert out_a.model_dump() == out_b.model_dump()  # deterministic
    assert out_a.n_alerts == 3
    assert out_a.n_labelled_positives == 2
    assert out_a.winner in ("champion", "challenger", "tie")
    assert set(out_a.champion.precision_at_k) == {"5", "10", "20"}


def test_leakage_allowlist_is_the_documented_feature_set():
    # The scorer must only ever read these per-alert feature keys; a regression
    # tripwire so a future field addition is a conscious decision.
    assert LEAKAGE_SAFE_FEATURES == frozenset(
        {"sum_amount", "amount", "count", "matched_row_ids"}
    )


def test_score_is_invariant_to_a_future_dated_field():
    # Injecting an unrelated/post-as_of field must NOT change the score —
    # proves the scorer has no temporal-leakage surface.
    from aml_framework.engine.prioritization import score_alert

    cfg = ProgramPrioritization(enabled=True)
    base = _alert("C0001", 90000, 9)
    leaked = {**base, "future_balance_next_month": 10_000_000, "as_of_plus_30d_count": 999}
    assert score_alert(base, _rule(), cfg).score == score_alert(leaked, _rule(), cfg).score
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_priority_outcome.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aml_framework.engine.priority_outcome'`

- [ ] **Step 3: Write the module**

```python
# src/aml_framework/engine/priority_outcome.py
"""Champion-challenger outcome analysis for the N1 prioritization scorer.

Scores historical LABELLED alerts with a champion and a challenger config,
computes precision@k + recall per config, and emits a deterministic
`priority_outcome.json` (SR 26-2 outcome analysis). Pure + reproducible.

Temporal-leakage guard: `score_alert` reads only the as-of feature keys in
`LEAKAGE_SAFE_FEATURES` off each alert dict — never a global/time lookup — so
a champion-challenger replay cannot bias scores with post-as_of data. The
allowlist + `test_score_is_invariant_to_a_future_dated_field` enforce it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.prioritization import score_alert

# The ONLY per-alert keys the scorer may read. A tripwire: adding a feature
# means consciously updating this set (and re-proving the leakage test).
LEAKAGE_SAFE_FEATURES = frozenset({"sum_amount", "amount", "count", "matched_row_ids"})

_DEFAULT_KS = (5, 10, 20)


class ConfigOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    precision_at_k: dict[str, float]
    recall: float
    mean_score: float
    weights: dict[str, float]


class PriorityOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    n_alerts: int
    n_labelled_positives: int
    k_values: list[int]
    champion: ConfigOutcome
    challenger: ConfigOutcome
    winner: str


def precision_at_k(ranked_ids: list[str], labels: dict[str, bool], k: int) -> float:
    """Fraction of the top-k ranked alerts whose customer is a labelled positive."""
    top = ranked_ids[:k]
    if not top:
        return 0.0
    hits = sum(1 for cid in top if labels.get(cid) is True)
    return round(hits / len(top), 6)


def recall_at_labels(ranked_ids: list[str], labels: dict[str, bool]) -> float:
    """Fraction of all labelled positives that appear anywhere in the ranking."""
    positives = {cid for cid, v in labels.items() if v is True}
    if not positives:
        return 0.0
    surfaced = positives & set(ranked_ids)
    return round(len(surfaced) / len(positives), 6)


def _score_rows(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    config: Any,
) -> list[tuple[float, str, str]]:
    """(score, rule_id, customer_id) for every alert under `config`."""
    rows: list[tuple[float, str, str]] = []
    for rule_id, alerts in alerts_by_rule.items():
        rule = rules.get(rule_id)
        if rule is None:
            continue
        for a in alerts:
            score = score_alert(a, rule, config).score
            rows.append((score, str(rule_id), str(a.get("customer_id"))))
    return rows


def _config_outcome(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    labels: dict[str, bool],
    config: Any,
    ks: tuple[int, ...],
) -> ConfigOutcome:
    rows = _score_rows(alerts_by_rule, rules, config)
    # Rank by score desc, deterministic tiebreak on (rule_id, customer_id).
    rows.sort(key=lambda t: (-t[0], t[1], t[2]))
    ranked_ids = [cid for _, _, cid in rows]
    w = config.weights
    return ConfigOutcome(
        precision_at_k={str(k): precision_at_k(ranked_ids, labels, k) for k in ks},
        recall=recall_at_labels(ranked_ids, labels),
        mean_score=round(sum(s for s, _, _ in rows) / len(rows), 6) if rows else 0.0,
        weights={
            "severity": w.severity,
            "risk_tier": w.risk_tier,
            "amount": w.amount,
            "volume": w.volume,
        },
    )


def build_priority_outcome(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    labels: dict[str, bool],
    *,
    champion: Any,
    challenger: Any,
    ks: tuple[int, ...] = _DEFAULT_KS,
) -> PriorityOutcome:
    """Deterministic champion-vs-challenger outcome on labelled alerts."""
    champ = _config_outcome(alerts_by_rule, rules, labels, champion, ks)
    chall = _config_outcome(alerts_by_rule, rules, labels, challenger, ks)
    max_k = str(max(ks))
    # Winner by recall, then precision@max-k. Deterministic, explainable.
    champ_key = (champ.recall, champ.precision_at_k[max_k])
    chall_key = (chall.recall, chall.precision_at_k[max_k])
    if champ_key > chall_key:
        winner = "champion"
    elif chall_key > champ_key:
        winner = "challenger"
    else:
        winner = "tie"
    n_alerts = sum(len(v) for v in alerts_by_rule.values())
    n_pos = sum(1 for v in labels.values() if v is True)
    return PriorityOutcome(
        enabled=True,
        n_alerts=n_alerts,
        n_labelled_positives=n_pos,
        k_values=list(ks),
        champion=champ,
        challenger=chall,
        winner=winner,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_priority_outcome.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Lint + commit**

Run: `ruff check src/aml_framework/engine/priority_outcome.py tests/test_priority_outcome.py && ruff format --check src/aml_framework/engine/priority_outcome.py tests/test_priority_outcome.py`
```bash
git add src/aml_framework/engine/priority_outcome.py tests/test_priority_outcome.py
git commit -m "feat(priority-outcome): champion-challenger backtest + leakage allowlist"
```

---

### Task 2: label CSV loader (reuse the backtest convention)

**Files:**
- Modify: `src/aml_framework/engine/priority_outcome.py`
- Test: `tests/test_priority_outcome.py`

- [ ] **Step 1: Write the failing test**

```python
def test_load_labels_csv(tmp_path):
    from aml_framework.engine.priority_outcome import load_labels_csv

    p = tmp_path / "labels.csv"
    p.write_text("customer_id,is_true_positive\nC0001,true\nC9999,false\nC0002,1\n")
    labels = load_labels_csv(p)
    assert labels == {"C0001": True, "C9999": False, "C0002": True}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_priority_outcome.py -k load_labels -q`
Expected: FAIL — `ImportError: cannot import name 'load_labels_csv'`

- [ ] **Step 3: Add the loader** (in `priority_outcome.py`)

```python
import csv
from pathlib import Path

_TRUE = {"true", "1", "yes", "y", "t"}


def load_labels_csv(path: Path) -> dict[str, bool]:
    """Parse a `customer_id,is_true_positive` CSV into {customer_id: bool}.
    Mirrors the `aml backtest --labels` convention."""
    labels: dict[str, bool] = {}
    with Path(path).open(newline="") as fh:
        for row in csv.DictReader(fh):
            cid = (row.get("customer_id") or "").strip()
            if not cid:
                continue
            labels[cid] = (row.get("is_true_positive") or "").strip().lower() in _TRUE
    return labels
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_priority_outcome.py -q` → PASS (7 passed)
```bash
git add src/aml_framework/engine/priority_outcome.py tests/test_priority_outcome.py
git commit -m "feat(priority-outcome): labels CSV loader"
```

---

### Task 3: runner writes `priority_outcome.json`; audit pins + freezes it

**Files:**
- Modify: `src/aml_framework/engine/runner.py` (mirror `_write_priority_report`)
- Modify: `src/aml_framework/engine/audit.py` (mirror `priority_report_hash` + frozen basenames)
- Test: `tests/test_priority_outcome.py`

> Read `runner.py:933` (`_write_priority_report`) and the call site at `runner.py:1505`, plus `audit.py:226` (`_FROZEN_SNAPSHOT_BASENAMES`) and `audit.py:536-592` (`priority_report_hash`) before editing — mirror them exactly.

- [ ] **Step 1: Write the failing integration test**

```python
def test_priority_outcome_written_pinned_and_frozen(tmp_path):
    import json
    import os

    from typer.testing import CliRunner
    from aml_framework.cli import app

    # community_bank + prioritization enabled
    import pathlib

    src = pathlib.Path("examples/community_bank/aml.yaml").read_text()
    src = src.replace(
        "  effective_date: 2026-01-01\n",
        "  effective_date: 2026-01-01\n  prioritization:\n    enabled: true\n",
        1,
    )
    spec = tmp_path / "p.yaml"
    spec.write_text(src)
    labels = tmp_path / "labels.csv"
    labels.write_text("customer_id,is_true_positive\nC0001,true\nC0002,true\n")
    out = tmp_path / "run"

    res = CliRunner().invoke(
        app,
        ["run", str(spec), "--seed", "42", "--out", str(out), "--labels", str(labels)],
    )
    assert res.exit_code == 0, res.output
    run_dir = sorted(out.glob("run-*"))[-1] if list(out.glob("run-*")) else out
    oc = run_dir / "priority_outcome.json"
    assert oc.exists()
    data = json.loads(oc.read_text())
    assert data["winner"] in ("champion", "challenger", "tie")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest.get("priority_outcome_hash")
    if os.name != "nt":
        assert (os.stat(oc).st_mode & 0o222) == 0  # frozen read-only
```

> NOTE: confirm the exact `aml run` output-dir flag + run-dir layout from `cli.py` `run` command before finalizing the test's `run_dir` resolution; adjust the glob to match (Step 1a).

- [ ] **Step 1a: Confirm `aml run` flags + run-dir layout**

Run: `aml run --help` and inspect `cli.py` `run` command. Confirm the output flag name (`--out` vs `--artifacts`) and whether a `run-*` subdir is created. Adjust the test's invocation + `run_dir` resolution to match the real layout before running.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_priority_outcome.py -k outcome_written -q`
Expected: FAIL — no `--labels` option on `aml run` (exit_code 2) or `priority_outcome.json` missing.

- [ ] **Step 3: Thread `--labels`/`--challenger-weights` + write the artifact**

Add `--labels: Path | None` and `--challenger-weights: str | None` (JSON) to the `aml run` command in `cli.py`; pass them into the runner. In `runner.py`, after `_write_priority_report(...)` and within the same `if _prioritization_cfg and .enabled` block, when labels are supplied:

```python
# runner.py — after the priority_report write, inside the enabled block
if labels_path is not None:
    from aml_framework.engine.priority_outcome import (
        build_priority_outcome,
        load_labels_csv,
    )

    labels = load_labels_csv(labels_path)
    champion = _prioritization_cfg
    challenger = _prioritization_cfg
    if challenger_weights:  # JSON dict of weight overrides
        import json as _json

        merged = {**_prioritization_cfg.weights.model_dump(), **_json.loads(challenger_weights)}
        challenger = ProgramPrioritization(enabled=True, weights=merged)
    rules_by_id = {r.id: r for r in spec.rules}
    outcome = build_priority_outcome(
        alerts_by_rule, rules_by_id, labels, champion=champion, challenger=challenger
    )
    (run_dir / "priority_outcome.json").write_text(
        outcome.model_dump_json(indent=2) + "\n"
    )
```

In `audit.py`: add `"priority_outcome.json"` to `_FROZEN_SNAPSHOT_BASENAMES` (line 226) and pin its hash in the manifest, mirroring `priority_report_hash`:

```python
# audit.py — beside priority_report_hash
outcome_path = self.run_dir / "priority_outcome.json"
priority_outcome_hash = (
    _sha256(outcome_path.read_bytes()) if outcome_path.exists() else None
)
# ... in the manifest dict:
"priority_outcome_hash": priority_outcome_hash,
```

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `python -m pytest tests/test_priority_outcome.py -k outcome_written -q`
Expected: PASS.

- [ ] **Step 5: Determinism cross-check**

Add + run a test that two runs with the same seed+as_of+labels produce equal `priority_outcome_hash` (mirror `test_prioritization_is_deterministic_across_runs`). Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
git add src/aml_framework/engine/runner.py src/aml_framework/engine/audit.py src/aml_framework/cli.py tests/test_priority_outcome.py
git commit -m "feat(priority-outcome): aml run --labels writes pinned+frozen priority_outcome.json"
```

---

### Task 4: docs + field lineage

**Files:**
- Modify: `README.md` (the `aml run` line — note `--labels` / `--challenger-weights`)
- Modify: `docs/spec-reference.md` (note the new `priority_outcome.json` artifact under prioritization) if prioritization has a section; else `docs/getting-started.md` advanced-spec section.

- [ ] **Step 1: Add the README note**

Append to the `aml run` line / add a sub-bullet:
```bash
aml run spec.yaml --labels labels.csv --challenger-weights '{"amount": 5.0}'  # champion-challenger priority_outcome.json (precision@k / recall)
```

- [ ] **Step 2: Run the docs-cli gate (run is already documented; this is additive prose)**

Run: `python -m pytest tests/test_docs_cli_coverage.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/spec-reference.md
git commit -m "docs(priority-outcome): document --labels champion-challenger outcome artifact"
```

---

### Task 5: full local gate

- [ ] **Step 1:** `python -m pytest tests/test_priority_outcome.py tests/test_prioritization.py -q` → all PASS.
- [ ] **Step 2:** `ruff check src/ tests/ && ruff format --check src/ tests/` → All checks passed.
- [ ] **Step 3:** `make ci-unit` → green. (`tests/test_priority_outcome.py` imports only stdlib + spec + engine — `.[dev]`-safe; no pandas/streamlit.)
- [ ] **Step 4:** Smoke: enable prioritization in a temp spec, `aml run … --labels labels.csv`, confirm `priority_outcome.json` + `manifest.priority_outcome_hash`.

---

## Self-Review

**Spec coverage (issue #483 acceptance):**
- Champion-challenger scoring of labelled alerts with precision@k / recall → Task 1 (`build_priority_outcome`, `precision_at_k`, `recall_at_labels`). ✓
- `priority_outcome.json` artifact, deterministic, manifest-pinned + audit-frozen like `priority_report.json` → Task 3 (runner write + audit pin/freeze + determinism test). ✓
- Temporal-leakage guard; regression that a future-dated feature is excluded → Task 1 (`LEAKAGE_SAFE_FEATURES` + `test_score_is_invariant_to_a_future_dated_field`). ✓
- Reuse existing precision/recall semantics → ranking-based p@k/recall implemented purely (the tuning set-based helpers don't rank); same TP/positives definitions. ✓ (noted divergence: p@k needs ranking, so a small new impl is justified — not a duplicate of `_precision`).
- Tests + docs + progress.md → Tasks 1–5 + PR.

**Placeholder scan:** none — every code step has complete code; the two real-layout uncertainties (`aml run` output flag/run-dir glob in Task 3·1a; whether `spec-reference.md` has a prioritization section in Task 4) have explicit verify-first steps.

**Type consistency:** `build_priority_outcome(alerts_by_rule, rules, labels, *, champion, challenger, ks)`, `precision_at_k(ranked_ids, labels, k)`, `recall_at_labels(ranked_ids, labels)`, `PriorityOutcome`/`ConfigOutcome`, `LEAKAGE_SAFE_FEATURES`, `load_labels_csv` are referenced identically across tasks. `priority_outcome_hash` manifest key + `priority_outcome.json` basename are consistent in runner/audit/tests.

## PR / wrap-up

- Codex → fix blockers → push → draft PR `Closes #483` + checklist + test plan.
- `docs/progress.md`: M3 round entry after merge.
- Engine/runtime change (new run artifact + audit field) → the dashboard/API containers gain no new surface, but the runner changed; **deploy is optional** — batch with M4 or deploy if a runtime smoke is warranted. Decide at merge: if only the artifact changed and no served endpoint differs, no deploy needed.
