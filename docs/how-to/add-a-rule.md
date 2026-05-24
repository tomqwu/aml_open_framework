# How to add a new detection rule

> **When you need this:** A new typology lands (FATF recommendation, an internal red flag, an examiner ask) and you need a rule that detects it — with a regulator-ready audit trail from day one.
>
> **Prereqs:** AML Open Framework installed (`pip install -e ".[dev]"`), a working `aml.yaml` from `examples/`, a working `data/input/` directory.
>
> **Time:** ~10 min for `aggregation_window`. Add 5 min for `custom_sql`, 10–15 min for `python_ref`.

There are four rule logic types. Pick the simplest one that expresses your typology — you can always escalate.

| Logic type | Best for | Auditability |
|---|---|---|
| `aggregation_window` | "More than N events of type X in a Y-day window" — the bulk of TM rules | Highest. Threshold + window are spec-declared, no SQL to review. |
| `list_match` | Sanctions / PEP / shell-vehicle name matching | Highest. Reference list version pinned on every alert. |
| `custom_sql` | Bespoke logic that doesn't fit a window aggregation | Medium. You write SQL — model-validation reviews the query. |
| `python_ref` | ML scorer / multi-source heuristic / anything algorithmic | Lower. Code lives in `src/aml_framework/models/`; needs SR 11-7 / E-23 / SS1/23 packaging. |

The example below uses `aggregation_window` — the most common case. See [How to wire a python_ref scorer](python-ref-scorer.md) for the algorithmic path.

---

## Steps

### 1 · Declare the rule in `aml.yaml`

Edit your spec's `rules:` block. Add:

```yaml
rules:
  - id: structuring_cash
    name: "Cash structuring under reporting threshold"
    severity: high           # critical / high / medium / low
    status: active           # active / pending_promotion / deprecated
    risk_tier: tier_1        # PR-RISK-1 — optional
    regulation_refs:
      - citation: "31 CFR §1010.314"
        description: "Structuring transactions to evade currency-reporting"
      - citation: "FATF R.10"
        description: "Customer due diligence in cash transactions"
    business_intent: >
      Catch customers depositing cash in amounts just below the $10K CTR
      threshold across multiple branches/days.
    out_of_scope:
      - "Wire transfers — addressed by `rapid_movement`"
      - "Single transactions > $10K — those are CTR-filing not TM-alerting"
    logic:
      type: aggregation_window
      source: txn                # data_contract id
      filter: "channel = 'cash' AND direction = 'inbound'"
      group_by: ["customer_id"]
      window: "14d"              # rolling 14-day window
      having:
        count:    { gte: 3 }     # 3+ events
        sum_amount: { gte: 9000, lt: 30000 }   # each window aggregates to $9K-$30K
    escalate_to: l1_aml_analyst  # workflow.queues id
    environments: ["dev", "test"]   # PR-D3 — promotion gate
    evidence:
      - "Customer transaction history (90 days)"
      - "KYC profile + occupation"
      - "Branch / channel mix"
```

### 2 · Validate the spec

```bash
aml validate examples/your_spec/aml.yaml
```

This does **two-layer validation**: JSON Schema (structural) → Pydantic (cross-reference integrity — `escalate_to` resolves to a real queue, `regulation_refs[].citation` is non-empty, `having` keys are valid, etc.).

If the spec is invalid you get a precise error message naming the field. Fix and re-run.

### 3 · Run against synthetic data

```bash
aml run examples/your_spec/aml.yaml --seed 42
```

Output goes to `.artifacts/run-<timestamp>/` (override with `--artifacts-root`). Look for `alerts/structuring_cash.jsonl` — if your rule fired, alerts are there.

### 4 · Open the dashboard and check the Alert Queue

```bash
aml dashboard examples/your_spec/aml.yaml
```

→ http://localhost:8501 → **Alert Queue** page → filter to your rule. You should see the rows that fired with their evidence panel + lineage chain populated.

### 5 · Verify the audit trail

```bash
aml verify-decisions .artifacts/run-<timestamp>
```

Should print `✓ chain valid, N decisions, head_hash=<sha>`. This is the same check a regulator can run.

---

## Verify it worked

Three things must be true:

1. **The rule appears in `manifest.json`** under `rule_outputs` with a `<rule_id>.jsonl.hash` SHA-256.
2. **`alerts/<rule_id>.jsonl` exists** with one line per alert. Each line has `customer_id`, `window_start`, `window_end`, `threshold` snapshot, and `reference_data_version` (per PR-PAY-1).
3. **Re-running with `--seed 42` produces identical bytes** — proven by `test_run_is_reproducible`. If `manifest.json` differs across runs, your rule is non-deterministic. Investigate.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `ValidationError: 'escalate_to' must reference a defined queue` | Queue ID typo or missing | Check `workflow.queues[].id` matches `escalate_to` exactly |
| Rule fires on every customer | `having` threshold too loose | Tune via the dashboard's Tuning Lab (page 23) before rolling to prod |
| Rule fires zero | `filter` SQL excludes everything | Check the `data_contract.id` is correct and the column you filter on actually has data |
| `rule_version` churns on every run | You're embedding mutable state in the rule | Move dynamic thresholds to spec params, not in `python_ref` code |

---

## What ships when this rule fires

A regulator-ready audit trail emerges automatically:

- `alerts/<rule_id>.jsonl` — each row carries `threshold` + `reference_data_version`
- `cases/<case_id>.json` — built when the runner opens cases for each alert
- `decisions.jsonl` — `case_opened` events stamped with `rule_version_hash(rule)`
- `field_lineage.jsonl` — alert-field → source-column lineage
- `defect_log.jsonl` — empty if rule healthy, populated if DQ exception fires while evaluating
- `monitoring_digest.json` — alert count rolls into the post-run digest

You write the rule. The framework writes the evidence.

---

## Next steps

- **Tune thresholds**: [Threshold Sensitivity page](../dashboard-tour.md) sweeps your `having` value at 0.5×/0.75×/1×/1.25×/1.5×/2× to show the alert count curve.
- **Promote across environments**: by default `environments: ["dev"]`. To move to prod: add `prod` to the list AND emit a sign-off event (see [How to promote a rule across environments](promote-rule.md)).
- **Add an ML scorer alongside**: [How to wire a python_ref scorer](python-ref-scorer.md) shows how to add a second rule that calls into an ML model in `src/aml_framework/models/`.
