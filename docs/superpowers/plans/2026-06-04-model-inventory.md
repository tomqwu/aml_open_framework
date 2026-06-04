# M2 — `aml model-inventory` CLI (N2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A spec-only `aml model-inventory <spec> [--out inventory.json] [--markdown inventory.md]` command that emits a deterministic, SR-26-2-shaped inventory of the **whole model population** — every rule (as a model), every `python_ref` external model, and the N1 prioritization scorer — so an MLRO can answer "what models do we have?" in one command without a run.

**Architecture:** A new pure generator `generators/model_inventory.py` builds the inventory dict + a markdown renderer, reusing `_resolve_tier`/`_resolve_cadence` from `generators/mrm.py`. It is **deterministic** (sorted, no wall-clock timestamp — unlike the existing rule-centric `build_inventory`, which uses `datetime.now()` and omits non-rule models). A thin Typer command in `cli.py` loads the spec and writes the artifact(s).

**Tech Stack:** Python 3.10+, Typer, Pydantic v2 spec models, pytest + Typer `CliRunner`.

---

## Background facts (verified against the codebase)

- `aml mrm-bundle` already builds per-rule MRM dossiers + a rule inventory **from a run dir**; `generators/mrm.py:build_inventory(spec)` builds a rule-tier inventory but (a) uses `datetime.now()` (non-deterministic), (b) iterates `spec.rules` only — it **misses** `python_ref` models-as-models and the N1 prioritization scorer. M2 is the **spec-only, whole-model-population** view, deterministic, covering those gaps. Do NOT modify `build_inventory`; add a sibling.
- Existing command named `inventory` is the **legacy-import** tool (`aml inventory <legacy.csv>`). M2 must use the distinct name **`model-inventory`**.
- `Rule` (spec/models.py:419+) fields used here: `id`, `name`, `severity`, `status`, `evaluation_mode`, `regulation_refs` (≥1), `logic` (discriminated union), `model_tier`, `validation_cadence_months`, `business_intent`, `risk_tier`, `owner` (`str | None`), `tags`, `evidence`.
- `RuleLogic.type ∈ {aggregation_window, list_match, custom_sql, python_ref, network_pattern}`. `PythonRefLogic` carries `callable` (`"mod.path:func"`), `model_id`, `model_version`.
- `spec.program.prioritization` is `ProgramPrioritization | None`; when `.enabled`, `.weights` is `PrioritizationWeights(severity, risk_tier, amount, volume)`. The scorer runs per-alert in `engine/prioritization.py` — it is NOT a rule.
- `spec.program` has `name`, `jurisdiction`, `regulator`, `owner`.
- Helpers to reuse from `generators/mrm.py`: `_resolve_tier(rule) -> "high"|"medium"|"low"` and `_resolve_cadence(rule) -> int` (validation cadence months). Module constants `GUIDANCE_VERSION`, `GUIDANCE_EFFECTIVE_DATE`.
- Loader: `from aml_framework.spec import load_spec` → `load_spec(path) -> AMLSpec` (JSON-Schema + Pydantic validation; raises on error).
- CLI command pattern (cli.py, e.g. `mrm-bundle` ~line 1523): `@app.command(name="...")`, `typer.Argument(..., exists=True, readable=True)`, `typer.Option(...)`, lazy `from aml_framework.generators... import ...` inside the function, `typer.echo`/console for output.
- Docs gate `tests/test_docs_cli_coverage.py`: every registered command must appear (as `` `aml model-inventory` `` or bare `aml model-inventory`) in README.md / getting-started.md / legacy-import.md / how-to/*.md, else the test fails. README mention is sufficient.
- CLI test idiom (`tests/test_auditor.py`): `CliRunner().invoke(app, ["model-inventory", str(spec), "--out", str(out)])`, assert `result.exit_code == 0` and the artifact exists/parses.

## File Structure

- **Create** `src/aml_framework/generators/model_inventory.py` — `build_model_inventory(spec) -> dict`, `render_model_inventory_markdown(inv) -> str`. Pure, deterministic, no wall-clock.
- **Modify** `src/aml_framework/generators/__init__.py` — export the two new functions.
- **Modify** `src/aml_framework/cli.py` — add the `model-inventory` command after `mrm_bundle_cmd`.
- **Create** `tests/test_model_inventory.py` — generator + CLI tests.
- **Modify** `README.md` — add `aml model-inventory` to the CLI block (satisfies the docs gate).
- **Modify** `docs/progress.md` — round entry (at PR/merge time, outside the per-task loop).

## Model-entry shape (the contract every task uses)

Each inventory entry (a "model") is a dict:
```python
{
    "model_key": str,        # stable id: rule id, or "prioritization_scorer"
    "kind": str,             # "rule" | "python_ref" | "scorer"
    "name": str,
    "purpose": str,          # business_intent or name (rule) / fixed (scorer)
    "tier": str,             # "high" | "medium" | "low"
    "cadence_months": int,   # validation cadence
    "owner": str,            # rule.owner or program.owner
    "conceptual_soundness": list[str],  # regulation refs / "weighted-linear" pointer
    "logic_type": str,       # rule.logic.type, or "weighted_linear" for the scorer
    "external_model": dict | None,  # {model_id, model_version, callable} for python_ref else None
    "last_outcome_analysis": None,   # spec-only view has no run; always None here
}
```

---

### Task 1: `build_model_inventory` — rule + python_ref entries

**Files:**
- Create: `src/aml_framework/generators/model_inventory.py`
- Test: `tests/test_model_inventory.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_model_inventory.py
from __future__ import annotations

import json

from aml_framework.generators.model_inventory import (
    build_model_inventory,
    render_model_inventory_markdown,
)
from aml_framework.spec import load_spec

SPEC = "examples/community_bank/aml.yaml"


def test_inventory_has_one_entry_per_rule():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    rule_keys = {m["model_key"] for m in inv["models"] if m["kind"] in ("rule", "python_ref")}
    assert rule_keys == {r.id for r in spec.rules}


def test_inventory_is_deterministic_byte_stable():
    spec = load_spec(SPEC)
    a = json.dumps(build_model_inventory(spec), sort_keys=True)
    b = json.dumps(build_model_inventory(spec), sort_keys=True)
    assert a == b  # no wall-clock / dict-order dependence


def test_inventory_sorted_by_tier_then_key():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    order = {"high": 0, "medium": 1, "low": 2}
    keys = [(order[m["tier"]], m["model_key"]) for m in inv["models"]]
    assert keys == sorted(keys)


def test_python_ref_entry_carries_external_model_block():
    # A python_ref rule must be flagged kind="python_ref" with model_id/version.
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    pyrefs = [m for m in inv["models"] if m["kind"] == "python_ref"]
    for m in pyrefs:
        assert m["external_model"] is not None
        assert set(m["external_model"]) == {"model_id", "model_version", "callable"}


def test_summary_counts_match():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    assert inv["summary"]["total_models"] == len(inv["models"])
    assert sum(inv["summary"]["by_kind"].values()) == len(inv["models"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_model_inventory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aml_framework.generators.model_inventory'`

- [ ] **Step 3: Write the generator (rule + python_ref entries; scorer added in Task 2)**

```python
# src/aml_framework/generators/model_inventory.py
"""Spec-only model-population inventory (SR 26-2 / OCC 2026-13).

Distinct from `generators/mrm.py:build_inventory` (rule-tier, run-aware,
wall-clock-stamped): this is the deterministic, spec-only view of EVERY model
in the programme — each rule, each `python_ref` external model, and the N1
prioritization scorer (which is not a rule). One command answers the MLRO's
"what is our model population?" without needing a run.

Pure + deterministic: sorted output, no wall-clock timestamp, so two calls on
the same spec are byte-identical.
"""

from __future__ import annotations

from typing import Any

from aml_framework.generators.mrm import (
    GUIDANCE_EFFECTIVE_DATE,
    GUIDANCE_VERSION,
    _resolve_cadence,
    _resolve_tier,
)
from aml_framework.spec.models import AMLSpec

_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}


def _rule_entry(rule: Any, program_owner: str) -> dict[str, Any]:
    is_pyref = rule.logic.type == "python_ref"
    external = None
    if is_pyref:
        external = {
            "model_id": rule.logic.model_id,
            "model_version": rule.logic.model_version,
            "callable": rule.logic.callable,
        }
    return {
        "model_key": rule.id,
        "kind": "python_ref" if is_pyref else "rule",
        "name": rule.name,
        "purpose": rule.business_intent or rule.name,
        "tier": _resolve_tier(rule),
        "cadence_months": _resolve_cadence(rule),
        "owner": rule.owner or program_owner,
        "conceptual_soundness": [r.citation for r in rule.regulation_refs],
        "logic_type": rule.logic.type,
        "external_model": external,
        "last_outcome_analysis": None,
    }


def build_model_inventory(spec: AMLSpec) -> dict[str, Any]:
    """Deterministic SR-26-2 model-population inventory for the whole spec."""
    program_owner = spec.program.owner
    models: list[dict[str, Any]] = [_rule_entry(r, program_owner) for r in spec.rules]

    models.sort(key=lambda m: (_TIER_ORDER[m["tier"]], m["model_key"]))

    by_kind: dict[str, int] = {}
    by_tier = {"high": 0, "medium": 0, "low": 0}
    for m in models:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        by_tier[m["tier"]] += 1

    return {
        "_guidance": GUIDANCE_VERSION,
        "_guidance_effective": GUIDANCE_EFFECTIVE_DATE,
        "programme": {
            "name": spec.program.name,
            "jurisdiction": spec.program.jurisdiction,
            "regulator": spec.program.regulator,
            "owner": program_owner,
        },
        "summary": {
            "total_models": len(models),
            "by_kind": by_kind,
            "by_tier": by_tier,
        },
        "models": models,
    }


def render_model_inventory_markdown(inv: dict[str, Any]) -> str:
    """Render the inventory as an MRM-review markdown table."""
    p = inv["programme"]
    lines = [
        f"# Model Inventory — {p['name']}",
        "",
        f"*{inv['_guidance']} (effective {inv['_guidance_effective']}) · "
        f"{p['jurisdiction']} · {p['regulator']} · owner: {p['owner']}*",
        "",
        f"**{inv['summary']['total_models']} models** — "
        + ", ".join(f"{k}: {v}" for k, v in sorted(inv["summary"]["by_kind"].items())),
        "",
        "| Model | Kind | Tier | Cadence (mo) | Owner | Purpose | Conceptual soundness |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in inv["models"]:
        refs = "; ".join(m["conceptual_soundness"])
        lines.append(
            f"| `{m['model_key']}` | {m['kind']} | {m['tier']} | {m['cadence_months']} "
            f"| {m['owner']} | {m['purpose']} | {refs} |"
        )
    return "\n".join(lines) + "\n"
```

> NOTE on `r.citation`: `regulation_refs` is a list of `RegulationRef`. Step 3a verifies the attribute name.

- [ ] **Step 3a: Verify the `RegulationRef` attribute name before running**

Run: `python -c "from aml_framework.spec.models import RegulationRef; print(list(RegulationRef.model_fields))"`
Expected: a list including the citation field. If the field is NOT named `citation` (e.g. it's `reference` or `ref`), update `_rule_entry`'s `conceptual_soundness` comprehension to the correct attribute before proceeding.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_model_inventory.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Lint**

Run: `ruff check src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py && ruff format --check src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py
git commit -m "feat(model-inventory): spec-only model-population inventory generator"
```

---

### Task 2: Add the N1 prioritization scorer as a model entry

**Files:**
- Modify: `src/aml_framework/generators/model_inventory.py`
- Test: `tests/test_model_inventory.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model_inventory.py`:

```python
def _spec_with_prioritization(tmp_path):
    import pathlib

    src = pathlib.Path(SPEC).read_text()
    block = "  effective_date: 2026-01-01\n  prioritization:\n    enabled: true\n"
    src = src.replace("  effective_date: 2026-01-01\n", block, 1)
    p = tmp_path / "prio.yaml"
    p.write_text(src)
    return load_spec(p)


def test_scorer_entry_present_when_prioritization_enabled(tmp_path):
    spec = _spec_with_prioritization(tmp_path)
    inv = build_model_inventory(spec)
    scorer = [m for m in inv["models"] if m["kind"] == "scorer"]
    assert len(scorer) == 1
    assert scorer[0]["model_key"] == "prioritization_scorer"
    assert scorer[0]["logic_type"] == "weighted_linear"
    assert scorer[0]["tier"] == "high"  # advisory triage on every alert = material


def test_scorer_absent_when_prioritization_disabled():
    spec = load_spec(SPEC)  # community_bank has no prioritization block -> disabled
    inv = build_model_inventory(spec)
    assert not [m for m in inv["models"] if m["kind"] == "scorer"]
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python -m pytest tests/test_model_inventory.py -k scorer -q`
Expected: FAIL — `test_scorer_entry_present_when_prioritization_enabled` finds 0 scorer entries.

- [ ] **Step 3: Add the scorer entry to `build_model_inventory`**

In `model_inventory.py`, add a helper and call it before the sort:

```python
def _scorer_entry(spec: AMLSpec) -> dict[str, Any] | None:
    prio = getattr(spec.program, "prioritization", None)
    if prio is None or not prio.enabled:
        return None
    w = prio.weights
    return {
        "model_key": "prioritization_scorer",
        "kind": "scorer",
        "name": "Alert Prioritization Scorer (N1)",
        "purpose": "Advisory SAR-likelihood triage score; re-orders queues, never changes disposition.",
        "tier": "high",  # touches every alert; advisory but material to triage
        "cadence_months": 12,
        "owner": spec.program.owner,
        "conceptual_soundness": ["transparent weighted-linear; score=sigmoid(Σ weight·feature)"],
        "logic_type": "weighted_linear",
        "external_model": None,
        "last_outcome_analysis": None,
        "weights": {
            "severity": w.severity,
            "risk_tier": w.risk_tier,
            "amount": w.amount,
            "volume": w.volume,
        },
    }
```

Then in `build_model_inventory`, after building rule entries:

```python
    models: list[dict[str, Any]] = [_rule_entry(r, program_owner) for r in spec.rules]
    scorer = _scorer_entry(spec)
    if scorer is not None:
        models.append(scorer)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_model_inventory.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint**

Run: `ruff check src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py && ruff format --check src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/generators/model_inventory.py tests/test_model_inventory.py
git commit -m "feat(model-inventory): include the N1 prioritization scorer as a model entry"
```

---

### Task 3: Export the new functions

**Files:**
- Modify: `src/aml_framework/generators/__init__.py`

- [ ] **Step 1: Add the exports**

Add to `generators/__init__.py` (mirror how `build_inventory` is exported):

```python
from aml_framework.generators.model_inventory import (
    build_model_inventory,
    render_model_inventory_markdown,
)
```

And add both names to `__all__` if the module defines one.

- [ ] **Step 2: Verify import resolves**

Run: `python -c "from aml_framework.generators import build_model_inventory, render_model_inventory_markdown; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Lint + commit**

Run: `ruff check src/aml_framework/generators/__init__.py`
```bash
git add src/aml_framework/generators/__init__.py
git commit -m "feat(model-inventory): export build_model_inventory + markdown renderer"
```

---

### Task 4: The `aml model-inventory` CLI command

**Files:**
- Modify: `src/aml_framework/cli.py` (add after `mrm_bundle_cmd`)
- Test: `tests/test_model_inventory.py`

- [ ] **Step 1: Write the failing CLI tests**

Add to `tests/test_model_inventory.py`:

```python
from typer.testing import CliRunner  # noqa: E402

from aml_framework.cli import app  # noqa: E402

_runner = CliRunner()


def test_cli_writes_json(tmp_path):
    out = tmp_path / "inv.json"
    result = _runner.invoke(app, ["model-inventory", SPEC, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["summary"]["total_models"] >= 1
    assert "models" in data


def test_cli_writes_markdown(tmp_path):
    out_md = tmp_path / "inv.md"
    result = _runner.invoke(app, ["model-inventory", SPEC, "--markdown", str(out_md)])
    assert result.exit_code == 0, result.output
    assert out_md.exists()
    assert out_md.read_text().startswith("# Model Inventory")


def test_cli_prints_summary_to_stdout(tmp_path):
    result = _runner.invoke(app, ["model-inventory", SPEC])
    assert result.exit_code == 0, result.output
    assert "models" in result.output.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_model_inventory.py -k cli -q`
Expected: FAIL — `exit_code == 2` (No such command 'model-inventory').

- [ ] **Step 3: Add the command in `cli.py`** (immediately after `mrm_bundle_cmd`)

```python
@app.command(name="model-inventory")
def model_inventory_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path | None = typer.Option(
        None, "--out", help="Write the inventory JSON here."
    ),
    markdown: Path | None = typer.Option(
        None, "--markdown", help="Write an MRM-review markdown table here."
    ),
) -> None:
    """Emit the SR-26-2 model-population inventory (rules + python_ref models +
    the N1 prioritization scorer) from the spec alone. Deterministic."""
    import json as _json

    from aml_framework.generators.model_inventory import (
        build_model_inventory,
        render_model_inventory_markdown,
    )
    from aml_framework.spec import load_spec

    spec = load_spec(spec_path)
    inv = build_model_inventory(spec)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(inv, indent=2, sort_keys=True) + "\n")
        typer.echo(f"Wrote model inventory JSON -> {out}")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_model_inventory_markdown(inv))
        typer.echo(f"Wrote model inventory markdown -> {markdown}")

    s = inv["summary"]
    typer.echo(
        f"{s['total_models']} models "
        f"(by kind: {dict(sorted(s['by_kind'].items()))}; "
        f"by tier: {s['by_tier']})"
    )
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `python -m pytest tests/test_model_inventory.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Lint**

Run: `ruff check src/aml_framework/cli.py tests/test_model_inventory.py && ruff format --check src/aml_framework/cli.py tests/test_model_inventory.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/aml_framework/cli.py tests/test_model_inventory.py
git commit -m "feat(model-inventory): aml model-inventory CLI command (N2)"
```

---

### Task 5: Docs — README CLI entry (satisfies the docs gate)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the command to the README CLI block**

Find the CLI block in `README.md` that lists `aml inventory` / `aml auditor-pack` and add a line:

```bash
aml model-inventory examples/community_bank/aml.yaml --out inventory.json --markdown inventory.md   # SR 26-2 model-population inventory
```

- [ ] **Step 2: Run the docs-coverage gate**

Run: `python -m pytest tests/test_docs_cli_coverage.py -q`
Expected: PASS — `aml model-inventory` is now documented.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(model-inventory): document aml model-inventory in README CLI block"
```

---

### Task 6: Full local gate

- [ ] **Step 1: Generator + CLI + docs tests**

Run: `python -m pytest tests/test_model_inventory.py tests/test_docs_cli_coverage.py -q`
Expected: all PASS.

- [ ] **Step 2: Lint the whole change**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: All checks passed.

- [ ] **Step 3: Full unit suite (the real CI parity)**

Run: `make ci-unit`
Expected: green. (No new pandas/streamlit imports → no skip-guard needed; `test_model_inventory.py` imports only json/typer/spec, all in `.[dev]`.)

- [ ] **Step 4: Smoke the command on an example**

Run: `aml model-inventory examples/community_bank/aml.yaml --markdown /tmp/mi.md && head -12 /tmp/mi.md`
Expected: prints "N models …" and the markdown table renders.

---

## Self-Review

**Spec coverage (issue #482 acceptance):**
- Generator builds inventory from a validated spec covering rules + python_ref + prioritization scorer → Tasks 1 + 2. ✓
- `aml model-inventory` CLI with `--out`/`--markdown` → Task 4. ✓
- Deterministic output (sorted, no wall-clock) → Task 1 `test_inventory_is_deterministic_byte_stable` + the no-timestamp design. ✓
- Feeds / aligns with MRM control matrix + audit pack → reuses `generators/mrm.py` tier/cadence helpers + same `GUIDANCE_*` constants (same SR-26-2 framing); does not duplicate `build_inventory`. ✓
- Unit tests over example specs covering every scoring rule + python_ref + scorer → Tasks 1/2/4. ✓
- Docs: README CLI block (docs gate) → Task 5; progress.md at PR time.

**Placeholder scan:** none — every code step has complete code; every run step has the exact command + expected output. The one attribute uncertainty (`RegulationRef.citation`) has an explicit verification step (1·3a) that tells the implementer how to correct it.

**Type consistency:** `build_model_inventory(spec) -> dict` and `render_model_inventory_markdown(inv) -> str` are referenced identically in Tasks 1/2/3/4. The model-entry shape (model_key/kind/name/purpose/tier/cadence_months/owner/conceptual_soundness/logic_type/external_model/last_outcome_analysis) is consistent across `_rule_entry`, `_scorer_entry`, the markdown renderer, and the tests. CLI command name `model-inventory` matches the test invocations and the docs entry.

## PR / wrap-up (outside the per-task loop)

- Codex review → fix blockers → push → draft PR `Closes #482` with TODO checklist + test plan.
- `docs/progress.md`: M2 round entry after merge.
- No runtime/container surface change (CLI only) → **no Azure deploy required** (per the docs/CLI-only precedent); the deploy reflex applies to API/dashboard/runtime changes.
