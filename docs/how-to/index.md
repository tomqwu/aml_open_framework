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

-   :material-magnify-plus:{ .lg .middle } **[Discover candidate typologies from a run](discover-typologies.md)**

    ---

    The offline `aml discover-typologies` CLI clusters a run's *unexplained* anomalies (no rule caught them) into `candidate_typologies.yaml` proposals (`status: pending_promotion`). Deterministic, human-gated, never auto-promoted. ~5 min. **Detailed.**

-   :material-graph-outline:{ .lg .middle } **[Detect mule rings from the identity graph](detect-mule-rings.md)**

    ---

    The offline `aml detect-mule-rings` CLI runs deterministic union-find + density community detection over the `resolved_entity_link` graph into a governed `mule_rings.json`. Surfaced on Network Explorer. Advisory — an investigator confirms, never auto-escalated. ~5 min. **Detailed.**

</div>

## Migrating + operating

<div class="grid cards" markdown>

-   :material-bank:{ .lg .middle } **[Migrate from SAS / Actimize / Mantas](../legacy-import.md)**

    ---

    The `aml inventory` + `aml import-legacy` wizard parses a legacy rule dump and produces a starter `rules:` block. Already a how-to.

-   :material-stairs-up:{ .lg .middle } **[Promote a rule across environments](promote-rule.md)**

    ---

    dev → test → uat → prod with sign-off events on the audit ledger. The `Program.environment` + `Rule.environments` machinery. ~5 min. **Detailed.**

-   :material-bitcoin:{ .lg .middle } **[Stand up a GENIUS Act PPSI program](genius-ppsi-compliance.md)**

    ---

    Walk the richer NPRM-grounded `genius_ppsi_stablecoin` spec end to end — 31 CFR Part 502 OFAC sanctions program, ISO 20022 fields, SAR + proposed PPSI CTR, filing-latency SLA, six stablecoin typologies. ~10 min. **Detailed.**

</div>

## Audit + evidence

<div class="grid cards" markdown>

-   :material-shield-check:{ .lg .middle } **[Verify the audit hash chain](verify-audit-chain.md)**

    ---

    Prove a `decisions.jsonl` hasn't been tampered with. CLI: `aml verify-decisions`. ~30 sec for a single run, ~5 min to wire into CI. **Detailed.**

-   :material-export:{ .lg .middle } **[Export per-case / per-batch evidence packs](export-case-pack.md)**

    ---

    Hand a regulator a single-case ZIP, not the whole run. `aml export-case` and `aml export-batch`. ~30 sec per export. **Detailed.**

-   :material-robot-outline:{ .lg .middle } **[Use the Case Copilot for a case](use-case-copilot.md)**

    ---

    Governed, in-page GenAI DRAFTS on the Case Investigation page (#499) — summarize / typology / draft STR-SAR narrative / counterparty network / risk. Human-reviewed, never auto-dispositions, audited as `ai_case_copilot_action`. Backend via `AML_AI_BACKEND`. ~2 min. **Detailed.**

-   :material-magnify-scan:{ .lg .middle } **[Walk the lineage chain for a case](walk-lineage.md)**

    ---

    Paste a case_id and trace it back to source rows. CLI: `aml lineage`. Dashboard: Lineage Explorer page. ~30 sec per case. **Detailed.**

-   :material-history:{ .lg .middle } **[Run a 5-year transaction-monitoring lookback](run-five-year-lookback.md)**

    ---

    The copy-paste runbook companion to the [5-year lookback architectural overview](../five-year-lookback.md). 60-month replay against the `community_bank_lookback` example + a deterministic synthetic generator. ~30–60 min wall time on a laptop. **Detailed.**

-   :material-whistle:{ .lg .middle } **[Run a FinCEN Whistleblower internal-channel audit](run-whistleblower-audit.md)**

    ---

    The offline `aml whistleblower-audit` CLI (#531) rolls SAR-backlog exposure, escalation coverage (documented reviewer + rationale), triage time, board-documented decisions, and ledger integrity out of a run's audit ledger into a frozen `whistleblower_audit_report.json` (+ `--markdown` board table + `--format nprm-gap`). Advisory readiness lens against [FR 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections). ~5 min. **Detailed.**

</div>

## Monitoring + DQ

<div class="grid cards" markdown>

-   :material-bell-ring:{ .lg .middle } **[Configure SLA monitoring](configure-sla.md)**

    ---

    `Program.sla` block + `sla_report.json` per-run artifact. ~5 min. **Detailed.**

-   :material-bug:{ .lg .middle } **[Triage defects from `defect_log.jsonl`](triage-defects.md)**

    ---

    Round 28's 11-category classifier + data/rule/mapping decision tree. ~2 min per defect. **Detailed.**

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
