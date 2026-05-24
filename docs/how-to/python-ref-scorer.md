# How to wire a `python_ref` scorer

> **When you need this:** A typology that can't be expressed as `aggregation_window` thresholds — multi-source heuristics, ML scorers, graph traversal, or anything algorithmic. The `python_ref` logic type is the framework's escape hatch from spec-as-data.
>
> **Prereqs:** [How to add a rule](add-a-rule.md) read — same spec workflow, just a different `logic.type`. Python ≥3.10. `xgboost` / `scikit-learn` if you're loading a real model (`pip install -e ".[ml]"`).
>
> **Time:** ~30 min for a deterministic heuristic. ~1-2h if you're packaging an ML model with `model_id` / `model_version` for SR 11-7 evidence.

`python_ref` invokes Python you write. The framework gives it a sandboxed view of the run's data + audit ledger, and expects an alerts list back. Everything else — versioning, lineage, manifest-hash pinning — comes for free if you follow the convention.

---

## Steps

### 1 · Declare the rule in `aml.yaml`

```yaml
rules:
  - id: mule_return_burst
    name: "Mule-return burst (pacs.004 amber-flag clustering)"
    severity: high
    risk_tier: tier_1
    regulation_refs:
      - citation: "ISO 20022 pacs.004"
        description: "Payment Return — reason codes AC03/AC04/MD07 indicate suspected mule activity"
    business_intent: >
      Detect customers whose recent ISO 20022 return-message activity shows
      a burst of pacs.004 returns with AC03/AC04/MD07 reason codes, especially
      with cross-border / shell-name beneficiaries.
    logic:
      type: python_ref
      module: aml_framework.models.mule_return_burst_scorer
      func: score
      # Optional — any parameters the scorer reads from spec
      params:
        return_count_threshold: 3
        country_fanout_threshold: 2
        shell_density_threshold: 2
      # Optional — for SR 11-7 / E-23 audit evidence
      model_id: "mule_return_burst_v3"
      model_version: "2026-05-24"
    escalate_to: l2_aml_investigator
    environments: ["dev", "test", "prod"]
    evidence:
      - "All pacs.004 return messages for the customer in the lookback window"
      - "Beneficiary jurisdiction map"
      - "Shell-name match against the BVI/PA registries"
```

### 2 · Implement the scorer

Create `src/aml_framework/models/mule_return_burst_scorer.py`:

```python
"""Mule-return burst detection.

Layered qualification per the spec's `business_intent`:

  Path A — snippet-equivalent ≥3 pacs.004 returns with AC03/AC04/MD07
  Path B — cross-signal: count ≥2 + beneficiary-country fan-out ≥2
           + shell-name density ≥2

Either path opens an alert. Both paths score against the SAME alert
payload schema so downstream lineage / audit-pack treat them uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class _Alert:
    customer_id: str
    rule_id: str
    window_start: datetime
    window_end: datetime
    matched_return_ids: list[str]
    return_count: int
    country_fanout: int
    shell_density: int
    score_path: str  # "A" or "B"


def score(
    *,
    spec_params: dict[str, Any],
    data: dict[str, list[dict[str, Any]]],
    as_of: datetime,
    lookback_days: int = 30,
    **_,
) -> list[dict[str, Any]]:
    """Required signature — kwargs are framework-injected.

    Args:
        spec_params: the `params:` block from `aml.yaml`
        data: dict of {contract_id: list-of-rows} as a DuckDB-loaded view
        as_of: the run's `as_of` datetime
        lookback_days: optional, defaults to 30
        **_: future-proof against the runner adding new kwargs

    Returns:
        list of alert dicts. Each must contain at minimum:
          rule_id, customer_id, window_start, window_end,
          matched_row_ids (or matched_return_ids).
        Everything else flows into the alert's metadata.
    """
    return_count_t = spec_params.get("return_count_threshold", 3)
    country_t = spec_params.get("country_fanout_threshold", 2)
    shell_t = spec_params.get("shell_density_threshold", 2)

    window_start = as_of - timedelta(days=lookback_days)
    txn_returns = data.get("txn_return", [])

    by_customer: dict[str, list[dict]] = {}
    for r in txn_returns:
        if r.get("reason_code") not in ("AC03", "AC04", "MD07"):
            continue
        if r.get("returned_at") < window_start:
            continue
        by_customer.setdefault(r["customer_id"], []).append(r)

    alerts: list[_Alert] = []
    for customer_id, returns in by_customer.items():
        n = len(returns)
        countries = {r.get("beneficiary_country") for r in returns}
        shells = sum(1 for r in returns if r.get("beneficiary_is_shell"))

        if n >= return_count_t:
            path = "A"
        elif n >= 2 and len(countries) >= country_t and shells >= shell_t:
            path = "B"
        else:
            continue

        alerts.append(_Alert(
            customer_id=customer_id,
            rule_id="mule_return_burst",
            window_start=window_start,
            window_end=as_of,
            matched_return_ids=[r["return_id"] for r in returns],
            return_count=n,
            country_fanout=len(countries),
            shell_density=shells,
            score_path=path,
        ))

    # Framework expects list-of-dict, not list-of-dataclass.
    return [a.__dict__ for a in alerts]
```

### 3 · Validate the spec + run

```bash
aml validate examples/your_spec/aml.yaml
aml run examples/your_spec/aml.yaml --seed 42
```

The runner:

1. Imports your module via `importlib`, sandboxed to the `aml_framework.models.*` namespace prefix (override with `AML_PYTHON_REF_PREFIX` for institution-specific scorers)
2. Calls your `score()` with the kwargs above
3. Captures returned alerts, normalizes (adds `threshold` snapshot + `reference_data_version` per PR-PAY-1), writes to `alerts/<rule_id>.jsonl`
4. Opens cases per alert + writes to `decisions.jsonl` with `rule_version_hash(rule)`
5. If your scorer raises: in **strict mode** (default) → run aborts with `PythonRefFailure` after recording the error in `defect_log.jsonl`; in **permissive mode** (`AML_STRICT_PYTHON_REF=0`) → run continues, defect is logged

### 4 · Verify it fired correctly

```bash
# 1. Alerts file present
cat .artifacts/run-.../alerts/mule_return_burst.jsonl | head -3

# 2. defect_log.jsonl is empty for this rule (no scorer errors)
grep mule_return_burst .artifacts/run-.../defect_log.jsonl

# 3. rule_version flows through
jq '.rule_version' .artifacts/run-.../cases/*.json | sort -u
```

### 5 · Add SR 11-7 / E-23 / SS1/23 model evidence

Because you set `model_id` + `model_version` on the rule, the framework adds them to every alert payload AND to the `program_intent.md` artifact in the regulator-ready ZIP. For the full model-risk evidence pack, add:

```yaml
# In your aml.yaml
program:
  nfrs:
    notes: |
      `mule_return_burst_v3` model card stored at
      `s3://bank-mrm/aml/models/mule_return_burst/v3/model_card.pdf`.
      Champion-challenger results: docs/model-cards/mule-return-burst.md.
      Validation cadence: every 6 months per SR 11-7.
```

---

## Verify it worked

Five checks:

1. **`alerts/<rule_id>.jsonl`** has rows, each with `customer_id`, `window_start`, `window_end`, `matched_return_ids`, `threshold`, `reference_data_version`.
2. **`defect_log.jsonl`** has zero entries for this rule (scorer didn't error).
3. **`monitoring_digest.json::alerts_per_rule`** includes your rule with a non-zero count.
4. **Re-run with `--seed 42`** produces identical bytes — proven by `test_run_is_reproducible`.
5. **Case file** has `rule_version` populated (PR-PAY-1 ensures this).

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: scorer module not on allowed prefix` | Your module is outside `aml_framework.models.*` | Either move it, or set `AML_PYTHON_REF_PREFIX=your_org.aml.scorers,aml_framework.models` |
| Strict-mode abort with `PythonRefFailure` | Scorer raised — check `defect_log.jsonl` for the traceback | Fix the exception or run with `AML_STRICT_PYTHON_REF=0` if you want permissive |
| Output bytes differ across runs (determinism break) | Iteration order over a `set` / `dict` not stable, or you hit `datetime.now()` somewhere | Sort everything before emit; only use `as_of` (passed in), never wallclock |
| Alerts missing `threshold` field | You returned the alert before the framework's normalization layer ran | Don't bypass — return plain dicts, let `_normalize_alerts_payload` (PR-PAY-1) stamp metadata |
| Model retraining churns `rule_version_hash` on EVERY run | You're embedding the model weights / timestamp into the rule spec | Move model artifact references OUT of the spec; pin only `model_id` + `model_version` strings |

---

## What ships when this rule fires

Same regulator-ready evidence emerges as for `aggregation_window`:

- Alert payload carries `rule_version` + `model_id` + `model_version`
- Audit pack `program_intent.md` enumerates the rule's `business_intent` + `out_of_scope`
- `defect_log.jsonl` captures any scorer exception with category `python_ref_failure`
- `monitoring_digest.json` includes it in the per-rule alert count + diff vs prior run

Plus an MRM advantage: because the model artifacts live in `src/aml_framework/models/` (or your institution-prefixed package), 2LoD reviews **the same code that fires the alert**. No black-box vendor model. No deserialization surprise.

---

## Next steps

- **Champion / challenger**: ship a second `python_ref` rule with `model_id: <same>_v4_candidate` running in parallel (`status: experimental`). Compare alerts in the Drift Monitor (page 50).
- **FP analysis**: the FP Analysis page (page 45) auto-clusters this rule's alerts by feature; you'll see threshold tuning opportunities without writing SQL.
- **Production deployment**: set `environments: ["prod"]` only after model validation pack is signed off. See [How to promote a rule across environments](promote-rule.md).
