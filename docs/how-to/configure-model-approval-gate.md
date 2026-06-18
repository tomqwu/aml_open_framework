# How to configure the model-approval gate

> **When you need this:** Your institution runs in `prod` + `strict_environment_gating` mode and you want to block any **material-tier** rule (i.e., `model_tier: medium` or `model_tier: high`) from executing in production until it has been formally approved by your model-risk committee. The model-approval gate (#529, North Star Pillar 7) implements this as an explicit `Rule.approval_status` field (`pending` / `approved` / `rejected`) with the gate opt-in controlled by `program.model_risk_monitoring.require_approval_before_prod`. Low-tier (`model_tier: low`) rules are never gated.
>
> **Prereqs:** A spec that has `program.model_risk_monitoring` declared and `program.environment: prod` + `program.strict_environment_gating: true`. The gate predicate lives in `engine/promotion.py`.
>
> **Time:** ~10 min to configure; ongoing for each new rule that enters medium/high tier.

The approval gate is **opt-in and explicit** — the gate does nothing unless you set `require_approval_before_prod: true` in the spec. When enabled and in prod-strict, the runner raises `EnvironmentGatingError` before executing any material-tier rule whose `approval_status` is not `approved`, and records an `approval_gate_check` event on `decisions.jsonl` (mirroring the existing `environment_gate_check` event). The disabled path emits nothing and is byte-identical to the pre-gate baseline.

---

## Steps

### 1 · Set the `model_tier` on every active rule

`model_tier` (low / medium / high) is an independent axis from `severity` (alert urgency) and `risk_tier` (control-risk classification):

- `low` — simple threshold rules, list-match rules, rules with no statistical component
- `medium` — aggregation rules with calibrated windows / thresholds; `python_ref` scorers with documented but non-complex logic
- `high` — ML scorers, graph-based rules, multi-factor composite models

```yaml
rules:
  - id: structuring_cash
    model_tier: low            # simple threshold — never gated
    approval_status: approved  # fine to set for completeness, has no effect
    ...

  - id: passthrough_funnel_scorer
    model_tier: medium         # calibrated scorer — gated in prod-strict
    approval_status: approved  # MRC approved 2026-05-14 — see DR-2026-047
    ...

  - id: graph_mule_scorer
    model_tier: high           # graph ML — gated in prod-strict
    approval_status: pending   # MRC review in progress
    ...
```

### 2 · Enable the gate in the program block

```yaml
program:
  environment: prod
  strict_environment_gating: true
  model_risk_monitoring:
    enabled: true
    require_approval_before_prod: true   # ← the gate switch
    ...
```

All three conditions must hold for the gate to fire:
- `require_approval_before_prod: true`
- `program.environment == "prod"`
- `program.strict_environment_gating == true`

If any is absent (dev environment, gate not opted in, non-strict mode) the runner proceeds as before — the gate emits nothing.

### 3 · Validate the spec

```bash
aml validate examples/your_spec/aml.yaml
```

With `--strict`, an active rule missing `risk_tier` is an error; the model-approval gate check happens at run time, not validate time. Validate confirms the spec is structurally sound.

### 4 · Run and observe gate behaviour

With `approval_status: pending` on a `model_tier: medium` rule:

```bash
aml run examples/your_spec/aml.yaml --seed 42
```

The runner raises:

```
EnvironmentGatingError: Rule 'graph_mule_scorer' (model_tier=high) is not approved
for production. Set approval_status: approved in the spec after MRC sign-off.
```

The `decisions.jsonl` ledger receives an `approval_gate_check` event immediately before the error, recording the rule ID, its tier, its current status, and the gate verdict — identical in shape to `environment_gate_check`.

### 5 · Approve a rule (after MRC sign-off)

Edit the rule in the spec:

```yaml
  - id: graph_mule_scorer
    model_tier: high
    approval_status: approved   # MRC approved 2026-06-15 — see DR-2026-061
```

Run again — the gate check now records `approved` and the rule executes normally. The `approval_status` field is excluded from `rule_version_hash` at its `pending` default, so approving a rule does not churn existing rule versions or break audit-trail continuity.

---

## Verify it worked

1. **Gate fires on pending rules:** set one medium/high rule to `approval_status: pending`, run in prod-strict mode, confirm `EnvironmentGatingError` with the correct rule ID.
2. **Gate passes on approved rules:** set `approval_status: approved`, re-run — no error, rule executes.
3. **Ledger records the check:** `jq 'select(.event_type == "approval_gate_check")' .artifacts/run-*/decisions.jsonl` shows one event per material-tier rule evaluated, with `verdict: blocked` or `verdict: approved`.
4. **Low-tier rules are never blocked:** set a `model_tier: low` rule to `approval_status: pending` — it runs normally regardless.
5. **Non-prod / non-strict gate is silent:** run with `program.environment: dev` or `strict_environment_gating: false` — no `approval_gate_check` events, no errors.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Gate never fires even on pending medium-tier rules | `require_approval_before_prod`, `environment`, or `strict_environment_gating` is not set | All three must be present; verify with `aml validate --strict` |
| `EnvironmentGatingError` on a `model_tier: low` rule | Not possible — low-tier rules are never gated by design | Confirm the rule's `model_tier` field is `low` |
| `approval_status` field not recognised | Spec not updated to v0.1.60+ schema | Run `aml validate` — it reports the schema version; pull latest `schema/aml-spec.schema.json` |
| Approving a rule changed its `rule_version_hash` | `approval_status` was set from the schema default (no `pending` explicit value) | `approval_status` is excluded from the hash at its `pending` default; setting `approved` increments the hash — this is correct model lifecycle behaviour |

---

## Next steps

- [Monitor model risk + drift](monitor-model-risk.md) — the `model_risk_report.json` surfaces each rule's `model_tier` + validation cadence; approval status feeds the MRM inventory.
- [Promote a rule across environments](promote-rule.md) — the dev → uat → prod promotion workflow; the approval gate is the final prod gate.
- [Triage defects](triage-defects.md) — when a gated rule produces unexpected output after approval, the defect triage decision tree applies.
