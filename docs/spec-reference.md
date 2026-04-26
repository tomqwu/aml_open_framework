# Spec Reference: `aml.yaml`

This is the field-by-field reference for the AML spec. The authoritative
contract is [`schema/aml-spec.schema.json`](../schema/aml-spec.schema.json) —
this document exists to explain intent.

## Top level

```yaml
version: 1                  # spec schema version; integer
program: { ... }            # who owns the program
data_contracts: [ ... ]     # declared input tables and columns
rules: [ ... ]              # detection rules, each with regulation refs
workflow: { ... }           # reviewer queues + escalation paths
reporting: { ... }          # regulator forms (optional)
retention_policy: { ... }   # retention windows per artifact class (optional)
metrics: [ ... ]            # program metrics with RAG bands (optional)
reports: [ ... ]            # audience-routed reports (optional)
```

## `program`

```yaml
program:
  name: community_bank_aml
  jurisdiction: US                    # ISO country code or region
  regulator: FinCEN                   # primary supervisor
  owner: chief_compliance_officer     # human owner of the program
  effective_date: 2026-01-01          # YYYY-MM-DD, when this version takes effect
```

## `data_contracts`

Declared inputs. The engine refuses to run if the warehouse schema does not
satisfy the contract.

```yaml
data_contracts:
  - id: txn
    source: raw.transactions          # fully-qualified source table/view
    freshness_sla: 1h                 # max lag before alerting
    columns:
      - { name: txn_id,      type: string,    nullable: false, pii: false }
      - { name: customer_id, type: string,    nullable: false, pii: true  }
      - { name: amount,      type: decimal,   nullable: false, constraints: [">0"] }
      - { name: currency,    type: string,    nullable: false }
      - { name: channel,     type: string,    enum: [cash, wire, ach, card] }
      - { name: direction,   type: string,    enum: [in, out] }
      - { name: booked_at,   type: timestamp, nullable: false }
    quality_checks:
      - { not_null: [txn_id, customer_id, amount, booked_at] }
      - { unique:   [txn_id] }
```

## `rules`

Each rule has:

- `id`, `name`, `severity` (`low | medium | high | critical`)
- `status` — `active | experimental | deprecated` (default `active`)
- `regulation_refs` — at least one; each with `citation` and `description`
- `logic` — one of the declarative types below, or an escape hatch
- `escalate_to` — initial queue id from `workflow.queues`
- `evidence` — what to attach to the case file
- `tags` — typology labels (e.g. `structuring`, `pep`); used by coverage metrics

### Logic type: `aggregation_window`

Most typologies (structuring, rapid movement, volume spikes) are windowed
aggregations.

```yaml
logic:
  type: aggregation_window
  source: txn                         # references a data_contract id
  filter:                             # optional row-level filter
    channel: cash
    direction: in
    amount: { between: [7000, 9999] }
  group_by: [customer_id]
  window: 30d                         # duration suffixes: s, m, h, d
  having:                             # post-aggregation conditions
    count:       { gte: 3 }
    sum_amount:  { gte: 25000 }
```

### Logic type: `list_match`

```yaml
logic:
  type: list_match
  source: customer
  field: full_name
  list: ofac_sdn                      # list id declared elsewhere
  match: fuzzy                        # exact | fuzzy
  threshold: 0.92                     # only for fuzzy
```

### Logic type: `custom_sql` (escape hatch)

```yaml
logic:
  type: custom_sql
  sql: |
    SELECT customer_id, SUM(amount) AS sum_amount
    FROM {{ source('txn') }}
    WHERE ...
    GROUP BY customer_id HAVING SUM(amount) > 100000
```

### Logic type: `python_ref` (escape hatch for ML scorers)

```yaml
logic:
  type: python_ref
  callable: models.anomaly:score      # module:function
  model_id: anomaly_v3
  model_version: 2026.03.1
```

## `workflow`

```yaml
workflow:
  queues:
    - id: l1_analyst
      sla: 24h
      next: [l2_investigator, closed_no_action]
    - id: l2_investigator
      sla: 72h
      next: [sar_filing, closed_no_action]
    - id: sar_filing
      regulator_form: FinCEN_SAR
      sla: 30d
```

## `reporting`

```yaml
reporting:
  forms:
    FinCEN_SAR:
      template: fincen_sar_v2
      mandatory_fields: [subject, narrative, triggering_rules, transactions]
    FinCEN_CTR:
      template: fincen_ctr_v1
      trigger: { channel: cash, aggregate_day: { gte: 10000 } }
```

## `retention_policy`

```yaml
retention_policy:
  evidence: 5y          # audit bundles
  alerts: 5y
  case_decisions: 5y
  raw_transactions: 7y  # depends on institution policy
```

Duration suffixes accepted by retention values: `s`, `m`, `h`, `d`, `y`.

## `metrics`

Program metrics with RAG bands. Each metric has an `id`, `category`
(`operational | effectiveness | risk | regulatory | delivery`), `audience`
(any of `svp`, `vp`, `director`, `manager`, `pm`, `developer`, `business`,
`auditor`, `analyst`), and a `formula`.

```yaml
metrics:
  - id: total_alerts
    name: Total Alerts
    category: operational
    audience: [manager, director]
    owner: head_of_aml_ops
    unit: count
    formula: { type: count, source: alerts }
    target: { value: 100 }
    thresholds:
      green: { lte: 100 }
      amber: { lte: 200 }
      red:   { gt: 200 }

  - id: alert_to_sar_rate
    name: Alert-to-SAR Conversion
    category: regulatory
    audience: [vp, auditor]
    formula:
      type: ratio
      numerator:   { type: count, source: cases, filter: { outcome: filed } }
      denominator: { type: count, source: alerts }

  - id: typology_coverage
    name: Typology Coverage
    category: effectiveness
    audience: [director]
    formula:
      type: coverage
      universe: typologies
      covered_by: rule_tags
```

Formula types: `count`, `sum`, `ratio`, `coverage`, `sql`. See
[`metrics-framework.md`](metrics-framework.md) for RAG semantics and audience
routing.

## `reports`

Audience-routed report definitions referencing metric ids.

```yaml
reports:
  - id: svp_exec_brief
    title: SVP Executive Brief
    audience: svp
    cadence: quarterly
    sections:
      - title: Program Health
        metrics: [total_alerts, alert_to_sar_rate, typology_coverage]
        commentary: Quarterly program-level RAG.
```

Cadences: `daily | weekly | monthly | quarterly | annual | on_demand`. Each
section's `metrics` list must reference declared `metrics[*].id` values —
cross-reference integrity is enforced at validation time.

## Versioning

`version: 1` is the spec *schema* version. The contents of `aml.yaml` are
versioned by git. The framework records both: the git SHA of the spec file
*and* a content hash, so you can detect accidental replay against the wrong
spec even in detached-HEAD situations.
