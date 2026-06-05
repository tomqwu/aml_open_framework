# How-to guides

Task-oriented recipes. Each one assumes you've completed [Getting Started](../getting-started.md) — pick the task you need and follow the steps.

## Building detectors

<div class="grid cards" markdown>

-   :material-rule:{ .lg .middle } **[Add a new detection rule](add-a-rule.md)**

    ---

    Declare an `aggregation_window` / `list_match` / `custom_sql` rule with full audit evidence from day one. ~10 min.

-   :material-code-braces:{ .lg .middle } **[Wire a python_ref scorer](python-ref-scorer.md)**

    ---

    Escape-hatch logic type for ML scorers, multi-source heuristics, graph traversal. Comes with SR 11-7 / E-23 / SS1/23 model evidence baked in. ~30 min.

</div>

## Migrating + operating

<div class="grid cards" markdown>

-   :material-bank:{ .lg .middle } **[Migrate from SAS / Actimize / Mantas](../legacy-import.md)**

    ---

    The `aml inventory` + `aml import-legacy` wizard parses a legacy rule dump and produces a starter `rules:` block. Already a how-to.

-   :material-stairs-up:{ .lg .middle } **[Promote a rule across environments](promote-rule.md)**

    ---

    dev → test → uat → prod with sign-off events on the audit ledger. The `Program.environment` + `Rule.environments` machinery. *(Placeholder — to be filled.)*

</div>

## Audit + evidence

<div class="grid cards" markdown>

-   :material-shield-check:{ .lg .middle } **[Verify the audit hash chain](verify-audit-chain.md)**

    ---

    Prove a `decisions.jsonl` hasn't been tampered with. CLI: `aml verify-decisions`. ~30 sec for a single run, ~5 min to wire into CI. **Detailed.**

-   :material-export:{ .lg .middle } **[Export per-case / per-batch evidence packs](export-case-pack.md)**

    ---

    Hand a regulator a single-case ZIP, not the whole run. `aml export-case` and `aml export-batch`. *(Placeholder — to be filled.)*

-   :material-magnify-scan:{ .lg .middle } **[Walk the lineage chain for a case](walk-lineage.md)**

    ---

    Paste a case_id and trace it back to source rows. CLI: `aml lineage`. Dashboard: Lineage Explorer page. *(Placeholder — to be filled.)*

-   :material-history:{ .lg .middle } **[Run a 5-year transaction-monitoring lookback](run-five-year-lookback.md)**

    ---

    The copy-paste runbook companion to the [5-year lookback architectural overview](../five-year-lookback.md). 60-month replay against the `community_bank_lookback` example + a deterministic synthetic generator. ~30–60 min wall time on a laptop. **Detailed.**

</div>

## Monitoring + DQ

<div class="grid cards" markdown>

-   :material-bell-ring:{ .lg .middle } **[Configure SLA monitoring](configure-sla.md)**

    ---

    `Program.sla` block + `sla_report.json` per-run artifact. *(Placeholder — to be filled.)*

-   :material-bug:{ .lg .middle } **[Triage defects from `defect_log.jsonl`](triage-defects.md)**

    ---

    Round 28's 11-category classifier + data/rule/mapping decision tree. *(Placeholder — to be filled.)*

-   :material-layers-triple:{ .lg .middle } **[Configure risk segmentation + governed suppression](configure-risk-segmentation.md)**

    ---

    Advisory de-prioritization of low-score alerts on low-risk customers via `program.risk_segmentation`. Never auto-closes; emits `suppression_report.json`. Requires `program.prioritization`. ~10 min. **Detailed.**

-   :material-monitor-dashboard:{ .lg .middle } **[Monitor model risk + per-rule drift](monitor-model-risk.md)**

    ---

    Governed model-risk monitoring via `program.model_risk_monitoring`. Emits a frozen, manifest-pinned `model_risk_report.json` (model inventory + per-rule count drift vs prior run + validation cadence). Advisory only; SR 11-7 / OSFI E-23. ~10 min. **Detailed.**

</div>

## Deploying

<div class="grid cards" markdown>

-   :material-cloud:{ .lg .middle } **[Deploy to Azure with federated identity](../deployment.md)**

    ---

    Terraform Container Apps + Postgres, Entra ID + Key Vault, workload identity. See the full [Deployment guide](../deployment.md).

</div>

---

## How-to guide template

Every page in this section follows the same shape:

```
# How to <verb> <noun>

> When you need this: <1-sentence trigger>
> Prereqs: <bullet list>
> Time: ~N min

## Steps
1. ...
2. ...

## Verify it worked
<one paragraph + a check>

## Common problems
| Symptom | Cause | Fix |

## Next steps
<links to related how-tos>
```

If a placeholder doesn't have content yet, it follows this template with the steps marked `TODO`. Want one filled in? File an issue or PR — the structure is intentional, so contributions can drop straight into the template.
