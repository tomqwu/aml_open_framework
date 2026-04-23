# Metrics & Reporting Framework

An AML program lives or dies by whether the right numbers land on the right
desks. This framework declares **metrics** and **reports** in the same
`aml.yaml` as the detection rules they describe, so everyone from the SVP
down to a platform engineer argues from one set of definitions.

## Why it's in the spec

If the VP sees an SLA-breach rate computed one way and the director computes
it another way, you have a governance problem, not a numbers problem. Pulling
metric *definitions* into the spec means:

- One PR changes the definition everywhere it's shown.
- Every metric declares an `owner`, an `audience`, and `thresholds` (RAG) —
  so the person being paged knows it's theirs.
- Metric values become part of the evidence bundle. A regulator can ask
  "what was your Q2 typology-coverage number?" and get a byte-exact answer
  alongside the alerts it was computed from.

## Declaring a metric

```yaml
metrics:
  - id: high_severity_alert_ratio
    name: High-severity alert share
    category: risk           # operational | effectiveness | risk | regulatory | delivery
    audience: [svp, vp, director]
    owner: chief_compliance_officer
    unit: "%"
    formula:
      type: ratio
      numerator:
        type: count
        source: alerts
        filter: { rule_id: { in: [structuring_cash_deposits] } }
      denominator:
        type: count
        source: alerts
    target:     { lte: 0.6 }
    thresholds:
      green: { lte: 0.6 }
      amber: { lte: 0.85 }
      red:   { gt:  0.85 }
```

### Formula types

| Type       | Computes                                                    |
|------------|-------------------------------------------------------------|
| `count`    | Row count of `source` (`alerts`, `cases`, `decisions`, `rules`, `txn`, `customer`) with an optional `filter` and optional `distinct_by` |
| `sum`      | Sum of `field` over `source` with optional `filter`         |
| `ratio`    | Nested formula over formula                                  |
| `coverage` | Share of a declared universe covered by fired rules         |
| `sql`      | Escape hatch — recorded in the audit ledger; executed by the institution's warehouse adapter in production |

### Targets and thresholds

- `target` is a single condition (`gte`, `lte`, `between`, `eq`) — "did we
  hit the goal?"
- `thresholds.{green,amber,red}` drive the RAG column in rendered reports.
  The first band whose condition holds wins.

## Declaring a report

```yaml
reports:
  - id: svp_exec_brief
    title: SVP executive brief
    audience: svp
    cadence: quarterly
    sections:
      - title: Outcomes
        metrics: [high_severity_alert_ratio, typology_coverage]
      - title: Exposure
        metrics: [distinct_customers_alerted, transaction_volume_usd]
```

Reports are just named arrangements of existing metrics. You can assemble a
director-level view and a manager-level view from overlapping subsets — the
metric is defined once and *quoted* by the reports that need it.

## Audience model

| Audience     | What they typically steer on                                 |
|--------------|--------------------------------------------------------------|
| `svp`        | Outcomes, risk posture, regulatory standing                   |
| `vp`         | Program effectiveness, typology coverage, exposure            |
| `director`   | Program health, demand, coverage, risk mix                   |
| `manager`    | Queue load, team throughput, SLA breach                      |
| `pm`         | Catalogue delivery, rule rollouts, throughput                |
| `developer`  | Runtime health, data freshness, rule execution stats         |
| `business`   | Customer impact — who's affected, how much volume is held    |
| `auditor`    | Control matrix, evidence completeness                        |
| `analyst`    | Operational detail, backlog                                  |

Any metric may list *multiple* audiences; any report is tagged with exactly
one (its primary reader).

## What gets produced per run

After rules execute, the runner:

1. Evaluates every metric against the run's alerts, cases, decisions, and
   input data.
2. Writes `metrics/metrics.json` with id, value, RAG, target hit.
3. Renders each declared report to `reports/<report_id>.md`.
4. Adds `metrics` and `reports` entries to `manifest.json` so they're part
   of the signed evidence bundle.

## Viewing reports

```
aml report examples/community_bank/aml.yaml                        # list reports
aml report examples/community_bank/aml.yaml --audience svp         # svp-only
aml report examples/community_bank/aml.yaml --report svp_exec_brief --stdout
```

## Collaboration flow

```
                   ┌──── aml.yaml (single source) ────┐
                   │                                  │
                   ▼                                  ▼
            rules + contracts                 metrics + reports
                   │                                  │
        generators (SQL, DAG)           metrics engine + renderer
                   │                                  │
              runtime alerts ─────────►  per-audience markdown
                                                      │
           ┌───────────┬───────────┬──────────────┬───┴──────┬────────────┐
           ▼           ▼           ▼              ▼          ▼            ▼
          SVP          VP       Director       Manager       PM       Developer
        quarterly    monthly    monthly         weekly      weekly     daily
```

Every role reads a different report. They all read **the same definitions**.
That is the collaboration contract this framework puts in place.
