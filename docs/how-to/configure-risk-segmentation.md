# How to configure risk segmentation + governed alert suppression

> **When you need this:** Your highest-likelihood alerts are buried under a long tail of low-score hits on customers your risk-based posture already treats as low-risk. You want to *de-prioritize* that tail so investigators reach the urgent work first — without ever auto-closing an alert or breaking the audit trail. The risk-segmentation block (#495) is the governed, advisory way to do it.
>
> **Prereqs:** `program.prioritization` **enabled** — risk segmentation gates on the advisory `priority_score` the prioritization scorer produces, so it does nothing without it. A spec that `aml validate` passes. `engine/suppression.py::score_suppression` is the canonical, pure decision function.
>
> **Time:** ~10 min.

Risk segmentation is **advisory de-prioritization only**. An alert flagged `suppression.applied=true` is *never* removed, re-disposed, re-queued, or auto-closed — the rule alert still lands in the ledger exactly as it would have. Suppression is a triage *lens* an investigator can override on the Triage Queue. It is explainable (every flag carries the segment, threshold, and score that produced it), reversible (`reversible: true`), and evidenced (the frozen, PII-masked `suppression_report.json` is one of the manifest-hashed artifacts).

---

## Steps

### 1 · Enable prioritization first (the precondition)

Risk segmentation has no score to gate on until the prioritization scorer runs. If it isn't already on, enable it:

```yaml
program:
  name: community_bank_aml
  prioritization:
    enabled: true
    # weights default to {severity: 1.0, risk_tier: 1.0, amount: 0.5, volume: 0.5}
```

With this alone, every alert gains a `priority_score` (see [`spec-reference.md`](../spec-reference.md) → `program.prioritization`). Confirm it works before adding segments — if the suppression pass ever reports `prioritization disabled — no priority_score`, this step is the cause.

### 2 · Declare a `risk_segmentation` block

Add the block alongside `prioritization`. Start with ONE low-risk segment and a modest threshold:

```yaml
program:
  prioritization:
    enabled: true
  risk_segmentation:
    enabled: true
    segments:
      - id: low_risk_retail
        field: customer_risk_rating      # v1 supports only this attribute
        values: [low]                    # customers whose risk_rating is "low"
        deprioritize_below: 0.25         # advisory: flag alerts scoring < 0.25
        rationale: >
          Low-risk retail customers below the 0.25 advisory score are worked
          after the urgent tail; tuned against Q1 FP analysis. Advisory only —
          never auto-closed.
        owner: mlro_2lod
```

`rationale` and `owner` are not decoration — they are the audit paper-trail for *why* these alerts may be triaged later and *who* signed off. Pick `deprioritize_below` modestly (0.2–0.3) so only the genuinely low-confidence tail is flagged; raise it later off FP-analysis evidence, as a spec PR.

### 3 · Validate

```bash
aml validate aml.yaml
```

Validation enforces the cross-reference integrity: `field` is constrained to `customer_risk_rating` (any other value is rejected, so the spec can never declare an attribute the engine silently ignores), `deprioritize_below` must be in `[0, 1]`, and `values` must be non-empty.

### 4 · Run

```bash
aml run aml.yaml --seed 42
```

The engine runs the rules unchanged, scores every alert (prioritization), then makes one post-scoring pass: for each alert whose customer is in a declared segment AND whose `priority_score` is strictly below that segment's `deprioritize_below`, it stamps `suppression.applied=true`. The pass is pure / deterministic / stdlib — same spec + same data + same seed yields identical flags.

### 5 · Read `suppression_report.json`

```bash
jq . .artifacts/run-*/suppression_report.json
```

The frozen, regulator-facing summary:

```json
{
  "enabled": true,
  "scored_alerts": 41,
  "suppressed": 7,
  "by_segment": { "low_risk_retail": 7 },
  "by_rule": { "structuring_burst": 5, "rapid_movement": 2 },
  "sample": [
    { "customer_id": "<masked>", "rule_id": "structuring_burst",
      "segment_id": "low_risk_retail", "priority_score": 0.11 }
  ]
}
```

`customer_id` is PII-masked with the same function the audit ledger applies to `alerts/*.jsonl`, so this artifact never persists a plaintext id. Its SHA-256 is pinned in `manifest.json` as `suppression_report_hash`.

### 6 · Work the queue on the dashboard

- **Triage Queue (page 52)** — scored alerts ranked by `priority_score`; advisory-suppressed alerts are visually de-emphasized but **still present and openable**. An investigator can **override** the suppression on any row — the override is the human-in-the-loop escape hatch the governance model requires.
- **FP Analysis (page 45)** — the suppression surface appears only when the run emitted `suppression_report.json`; it shows how many alerts each segment / rule de-prioritized, so you can tune `deprioritize_below` against the actual false-positive tail.

---

## Verify it worked

Three checks:

1. **`suppression_report.json` exists** in the run dir and `manifest.json::suppression_report_hash` matches `sha256(suppression_report.json)`.
2. **No alert disappeared** — the rule alert count in `decisions.jsonl` is identical with and without the block. Suppression only ADDS a `suppression` key; it never removes an alert. Diff a run with `risk_segmentation.enabled: false` against one with it `true`: same alerts, same dispositions, only the `suppression` field differs.
3. **Determinism** — re-run with the same seed; `suppression_report_hash` is unchanged.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Every alert reports `prioritization disabled — no priority_score` | `program.prioritization` not enabled — suppression has no score to gate on | Enable `prioritization` (Step 1); the suppression pass is a deliberate no-op without it |
| `suppression_report.json` absent | `risk_segmentation` omitted or `enabled: false` | Add/enable the block; the runner emits the report only when the pass runs |
| Nothing suppressed despite low-risk customers | No alert scored *below* `deprioritize_below`, or no customer's `risk_rating` is in `values` | Raise the threshold modestly, or confirm the customer `risk_rating` column actually carries the segment `values` |
| Validation rejects `field: customer_segment` | v1 supports ONLY `customer_risk_rating` | Use `customer_risk_rating`; other attributes are a future Literal-widening extension |

---

## Next steps

- [`spec-reference.md`](../spec-reference.md) — `program.risk_segmentation` and `program.prioritization` field-by-field.
- [How to verify the audit chain](verify-audit-chain.md) — `suppression_report.json` is one of the manifest-hashed artifacts; the advisory flags are evidenced, not free-floating.
- [How to triage defects](triage-defects.md) — the sibling triage lens. Suppression de-prioritizes; defects classify *why something didn't fire right*. Both are advisory; the deterministic rules stay authoritative.
