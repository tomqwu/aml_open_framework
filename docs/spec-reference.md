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
  ai_audit_log: hash_only             # what the GenAI assistant writes to ai_interactions.jsonl

  # ── Optional blocks (omit when not needed) ──────────────────────
  environment: dev                    # promotion lane: dev | test | uat | prod
  strict_environment_gating: false    # raise on rule env-mismatch when True
  sla:                                # Pillar-6 SLA monitor (PR-LF1)
    alert_disposition_days: 30
    batch_cadence_days: 1
    batch_lateness_grace_days: 1
  legacy_reference:                   # parallel-run equivalence (PR-EQ-1)
    path: ./legacy-alerts.csv         # required
    format: csv                       # optional: csv | parquet | jsonl (default csv)
    key_columns: [customer_id, alert_window_end]   # required
    rule_map:                         # optional: new_rule_id → legacy_rule_id
      structuring_burst: LEGACY_RULE_42
  nfrs:                               # non-functional requirements (PR-D2)
    rto_minutes: 240                  # optional
    rpo_minutes: 60                   # optional
    sla_p95_ms: 5000                  # optional
    throughput_per_min: 200           # optional
    retention_days: 2555              # optional (7y for AML)
    notes: "MRM validation cadence + BCP/DR posture"
```

**`ai_audit_log`** (default `hash_only`) controls what the dashboard's GenAI assistant retains in the run's append-only `ai_interactions.jsonl` file:

- `hash_only` — logs SHA-256 of every reply text. Bounds PII transit to disk; the full reply lives only in the operator's session and disappears on refresh. Privacy-safe default.
- `full_text` — logs the entire reply for forensic recall. Institutions opt into this only after clearing it against their privacy posture; the spec change is itself the paper trail.

Other audit fields (`ts`, `page`, `persona`, `backend`, `citations`, `confidence`, `referenced_metric_ids`, `referenced_case_ids`, `question`) are always logged regardless of mode.

### Optional blocks

**`environment`** (default `dev`) — the promotion lane this spec is running in. Allowed: `dev | test | uat | prod`. Combined with each rule's `environments` list, the engine warns (or with `strict_environment_gating: true`, raises `EnvironmentGatingError`) when a rule fires in a lane it wasn't approved for. Greenfield deployments leave this at `dev` until the promotion process is wired up. *PR-D3 / Round 28.*

**`strict_environment_gating`** (default `false`) — opt-in to hard-fail on environment mismatches instead of warning. Institutions flip this once the rule lifecycle workflow is signing off rule promotions across lanes. *PR-D3 / Round 28.*

**`sla`** (default `None`) — Pillar-6 SLA monitor declaration. Three sub-fields, all optional with sensible defaults:

- `alert_disposition_days` (default `30`) — max age in days before an open alert is a breach. The engine counts cases with a `case_opened` event older than this threshold and no terminal decision (`closed` / `escalated_to_str`) in the audit ledger.
- `batch_cadence_days` (default `1`) — expected cadence of the data extract.
- `batch_lateness_grace_days` (default `1`) — grace window before a late batch is flagged. The engine compares `run.as_of` to the most-recent transaction timestamp; a gap larger than `cadence + grace` flags the run as a lateness breach.

Engine never raises on SLA breach; it records the breach in `sla_report.json` for downstream surfaces (manifest-hash pinned). Omitting the block disables the monitor. *PR-LF1 / Round 27.*

**`legacy_reference`** (default `None`) — pointer to a legacy alert export for parallel-run divergence classification. Required: `path` + `key_columns`. Optional: `format` (`csv | parquet | jsonl`, default `csv`), `dataset` (for multi-table formats), `rule_map` (**new → legacy** rule id mapping; keys are this spec's `rule_id`s, values are the corresponding legacy-system identifiers). Consumed by `engine/equivalence.py` and the Equivalence dashboard page (pages/48). Engine ignores at runtime — equivalence is a separate read-only synthesis. *PR-EQ-1 / Round 26.*

**`nfrs`** (default `None`) — non-functional requirements declaration. Six optional fields: `rto_minutes`, `rpo_minutes`, `sla_p95_ms`, `throughput_per_min`, `retention_days`, `notes` (free-form prose for MRM context, validation cadence, regulatory commitments). Surfaces feed it into capacity planning, BCP/DR posture, and the regulator audit pack. Engine ignores at runtime. *PR-D2 / Round 27.*

**`prioritization`** (default `None`) — governed alert triage score. Advisory, explainable scoring that ranks alerts by risk without ever changing their disposition. Two sub-fields:

- `enabled` (default `false`) — activate the scorer. When `false` (or the block is omitted), the engine runs unchanged and no `priority_score` fields appear.
- `weights` (default `{severity: 1.0, risk_tier: 1.0, amount: 0.5, volume: 0.5}`) — per-feature multipliers for the logistic scorer. Four features:
  - `severity` — ordinal urgency of the rule (`low=0.25 / medium=0.5 / high=0.75 / critical=1.0`).
  - `risk_tier` — risk-based-controls posture of the rule (`low=0.33 / medium=0.66 / high=1.0`; `None`→0).
  - `amount` — log-scaled transaction amount, capped at $100 000 → [0, 1].
  - `volume` — transaction count behind the alert, capped at 50 → [0, 1].

Each scored alert gains two fields: `priority_score` (float 0–1, sigmoid of the weighted sum) and `priority_explanation` (list of `{feature, value, contribution}` dicts — one per feature plus a bias term). The engine emits `priority_report.json` in the run directory (frozen read-only, SHA-256 hash pinned in `manifest.json` as `priority_report_hash`). Score is deterministic: same spec + same data + same seed → identical scores → identical hash. *PR-PRIO / Round 33.*

**Champion-challenger outcome analysis (M3).** When prioritization is enabled and `aml run` is given `--labels <csv>` (a `customer_id,is_true_positive` ground-truth file), the engine additionally emits `priority_outcome.json` — a deterministic SR-26-2 outcome artifact scoring every alert with the champion (the spec's weights) and a challenger (`--challenger-weights '{"amount": 5.0}'`), reporting `precision@k` + `recall` per config and a `winner`. Frozen read-only and pinned in `manifest.json` as `priority_outcome_hash`, like `priority_report.json`. The scorer reads only as-of alert features (no future-dated lookups) — a temporal-leakage guard proven by `test_score_is_invariant_to_a_future_dated_field`.

## `data_contracts`

Declared inputs. The engine refuses to run if the warehouse schema does not
satisfy the contract. External data sources (CSV, Parquet, DuckDB, warehouse,
S3/GCS) also fail closed when a declared contract is missing or unloadable;
use `allow_empty: true` only for contracts that are intentionally optional or
empty in a reviewed deployment.

```yaml
data_contracts:
  - id: txn
    source: raw.transactions          # fully-qualified source table/view
    freshness_sla: 1h                 # max lag before alerting
    allow_empty: false                # fail closed if source is missing/unloadable
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

#### Point-in-time enrichment — `enrich` (M4 / #484)

To evaluate a rule against reference state **as of each transaction's date**
(not the latest row), declare the reference contract as `effective_dated` and
add an `enrich` block to the aggregation window. The engine emits an as-of JOIN
(`ref.valid_from <= booked_at AND (ref.valid_to IS NULL OR booked_at < ref.valid_to)`),
so a customer whose `risk_rating` changed mid-window is scored on the value in
force at each txn — closing the Pillar-3 SCD-2 gap.

```yaml
data_contracts:
  - id: customer
    effective_dated: { valid_from: valid_from, valid_to: valid_to }  # valid_to optional/null = current
    columns:
      - { name: customer_id, type: string,    nullable: false }
      - { name: risk_rating, type: string }
      - { name: valid_from,  type: timestamp, nullable: false }
      - { name: valid_to,    type: timestamp, nullable: true  }
rules:
  - id: high_risk_burst
    logic:
      type: aggregation_window
      source: txn
      group_by: [customer_id]
      window: 30d
      having: { count: { gte: 2 } }
      enrich:
        contract: customer                       # must be effective_dated
        key: customer_id                         # join key (named `key`, not `on` — YAML 1.1 coerces `on:` to true)
        where: ["customer.risk_rating = 'high'"] # raw predicates over the joined contract
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

### Logic type: `network_pattern`

Detects patterns over the entity-resolution graph. The engine maintains a `resolved_entity_link` table (pairs of customers sharing a linking attribute); the rule runs a recursive CTE up to `max_hops` from each seed customer and flags subgraphs satisfying the `having` condition.

```yaml
logic:
  type: network_pattern
  source: customer                    # accepted in spec but the executor seeds
                                      # ONLY from the `customer` table today
                                      # (engine/runner.py:_execute_network_pattern,
                                      # engine/lineage.py:311). Leave as `customer`.
  pattern: component_size             # component_size | common_counterparty
  max_hops: 2                         # 1..5; how far to walk the link graph
  having:
    # Keys MUST be one of the metric names the executor emits:
    # `component_size` or `counterparty_count` (always both emitted
    # regardless of `pattern`). `having: {common_counterparty: ...}`
    # validates against the schema but silently produces zero alerts.
    component_size: { gte: 3 }        # e.g. flag clusters of ≥3 linked customers
```

The `pattern` field is a hint to operators / surfaces about which metric the rule is meant to highlight — the executor always computes both and gates on whatever `having` keys you write.

Patterns:

- **`component_size`** — number of distinct customers in the connected component reachable from the seed within `max_hops` (includes the seed).
- **`common_counterparty`** — counterparty-overlap rule; the gating metric to use in `having` is **`counterparty_count`**, computed by `_execute_network_pattern` as `COUNT(DISTINCT reached_id)` excluding the seed itself. A hub linked to four other customers (any combination of link attributes) scores `counterparty_count = 4`. Useful for ring / pass-through detection.

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
