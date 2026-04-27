# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does not
yet use semantic version tags, so entries are grouped by merge date and the PR
that introduced them.

## [Unreleased]

### Added
- **Counterparty-VASP attribution layer** (`vasp/` package,
  `data/lists/sample_walletlabels.csv`). Round-4 PR #4 of 4 — the
  **dark-horse winner** of the Round-4 research scan. Closes the
  gap between "block this OFAC-listed wallet" (already covered by
  `list_match` against `sanctioned_wallets.csv`) and "score the
  counterparty of every crypto transfer based on its full
  attribution profile" — the high-margin Chainalysis / TRM Labs
  / ComplyAdvantage paid capability. **OFAC's January 2026
  designation of UK-registered Zedcex/Zedxion** (tens of billions
  in IRGC-linked flows) and the **Tornado Cash delisting
  (March 2025)** moved the field from "block this address" to
  "score this counterparty's attribution profile" — single-address
  blocklists are no longer sufficient.
  Three abstractions:
  - **`VaspAttribution`** — frozen dataclass with `address`,
    `cluster_name`, `tier` (tier_1/tier_2/tier_3/mixer/ransomware/
    darknet/sanctioned/unknown), `jurisdiction`, `source`, `flags`
    (free-form indicators like `iran_nexus`,
    `pig_butchering_nexus`), and `confidence` (commercial feeds
    can override).
  - **`VaspAttributionStore`** — in-memory address → attribution
    lookup with case-insensitive normalisation, by_tier filter,
    addresses_in_cluster reverse index, last-write-wins on
    duplicates. Production swaps in Redis/Postgres behind the
    same interface.
  - **`enrich_transactions(txns, store)`** — pure function that
    annotates each txn with a `counterparty_vasp` block. Source
    txns are NOT mutated (returns new dicts). Unattributed
    counterparties get `counterparty_vasp: None` so downstream
    rules can treat "unknown" as a distinct case.
  Two adapters in v1 — same `name + load(path) → list[VaspAttribution]`
  shape as the `sanctions/` adapters from PR #44:
  - **`OFACCryptoAddressesSource`** — parses OFAC's text-format
    crypto bundle (`XBT 1addr (Entity)`, `ETH 0xaddr (Entity)`,
    etc) covering 10 supported chains.
  - **`WalletLabelsSource`** — parses the de-facto-standard
    `walletlabels.csv` schema (address, label, category,
    jurisdiction, optional flags) used by Etherscan,
    walletexplorer.com cluster exports, etc.
  Bundled `sample_walletlabels.csv` ships with 6 placeholder
  entries (Coinbase tier_1, Tornado Cash mixer, Zedcex sanctioned,
  Huione sanctioned with `pig_butchering_nexus` flag composing
  with PR #54, a P2P swap tier_3, and a LockBit ransomware
  cluster) so operators can run the layer end-to-end without
  external feeds. **Public-data only** by design — production
  VASP de-risking layers commercial enrichment on top via the
  same interface; the engine doesn't care which provider
  populated the attribution.
  27 new tests under `TestOFACCryptoParser`, `TestWalletLabelsParser`,
  `TestVaspAttributionStore`, `TestEnrichTransactions`,
  `TestLoadIntoStore`, and `TestEndToEndComposition` cover all
  10 supported chains, entity-in-parens parsing, blank/comment
  tolerance, category-to-tier mapping, jurisdiction normalisation,
  flag splitting, case-insensitive address lookup, last-write-wins
  semantics, by_tier filtering, source-txn immutability, address-
  field override, multi-source bulk-load, and end-to-end
  "filter to sanctioned counterparty" demonstration that mirrors
  the shape a `list_match` rule would take.
- **Cyber-enabled fraud / pig-butchering example spec**
  (`examples/cyber_enabled_fraud/aml.yaml`,
  `data/lists/pig_butchering_nexus.csv`). Round-4 PR #3 of 4. New
  typology-focused example spec demonstrating detection of
  pig-butchering / authorised-push-payment fraud — the single
  fastest-growing cyber-enabled fraud typology of 2025-2026 (UK
  40% of all crime; Singapore +61% in two years; FBI IC3 reports
  $5.8 B in US losses 2024). Composes existing primitives, no
  engine changes:
  - `pig_butchering_payout_fan` — `network_pattern` rule (PR #49)
    detecting outbound cluster convergence on crypto on-ramps
    (component_size ≥ 3 inside 2 hops). Catches the classic
    victim → mule → exchange → cash-out shape even when the
    customer doesn't realise it.
  - `ramp_up_then_drain` — `aggregation_window` rule modelling
    the FinCEN advisory pattern: ≥3 priming outbound transfers
    (<$500) to a new beneficiary inside 14 days. Ships with a
    `tuning_grid` so MLROs can sweep the count + sum_amount
    thresholds (PR #50).
  - `pig_butchering_nexus_screening` — `list_match` rule against
    bundled `pig_butchering_nexus.csv` seeded with FinCEN
    Section 311 designations (Huione Group + subsidiaries).
  Citations: FATF Cyber-Enabled Fraud paper (Feb 2026), FinCEN
  FIN-2023-Alert005 (SAR Advisory Key Term: PIG BUTCHERING),
  FinCEN Section 311 Huione (May 2025), 31 CFR § 1020.320 (BSA
  SAR), 31 CFR § 1010.658 (Section 311 special measures). The
  spec composes naturally with PR #45 narrative drafter
  (auto-cite FATF/FinCEN), PR #46 pKYC (new-beneficiary trigger),
  PR #49 explainability (Mermaid subgraph in the STR), PR #43/48
  goAML/AMLA exporters, PR #50 Tuning Lab. No other open-source
  AML framework ships a pig-butchering rule pack today. 9 new
  tests under `TestCyberEnabledFraudSpec` cover spec validation,
  three-logic-type composition, severity routing, `tuning_grid`
  declaration on `ramp_up_then_drain`, FATF + FinCEN
  regulation-ref coverage, bundled-list existence with Huione
  cite, `str_filing` workflow queue + `fincen_sar` form presence,
  and end-to-end run on synthetic data (zero-positives by design
  — synthetic generator doesn't plant pig-butchering shapes; the
  spec must still execute cleanly against the example dataset).
- **Effectiveness Evidence Pack** (`generators/effectiveness.py`,
  `cli.py:effectiveness-pack`, `Rule.aml_priority` spec field).
  Round-4 PR #1 of 2 (paired with the upcoming MRM bundle for
  SR 26-2). FinCEN's **2026-04-07 NPRM** ("Reform of the AML/CFT
  Programs Requirements") moves examiners from "existence" to
  "effectiveness" standards — every BSA-covered institution will
  need to *prove* program effectiveness against the FinCEN
  AML/CFT priorities. This generator builds that proof from
  artifacts the framework already produces. Output is a single
  structured JSON document mapped to the four NPRM pillars:
  - **Risk-assessment alignment** — counts rules with
    `regulation_refs`, severity distribution.
  - **AML/CFT priority coverage** — uses the new
    `Rule.aml_priority` enum field to bucket rules by FinCEN
    priority (corruption, cybercrime, terrorist_financing, fraud,
    transnational_criminal_organization, drug_trafficking,
    human_trafficking, proliferation_financing, other); flags
    unmapped rules as gaps requiring MLRO classification.
  - **Control output quality** — alert volume, false-positive
    proxy (closed_no_action / total dispositions from
    `decisions.jsonl`), narrative-review acceptance rate,
    `tuning_run` event count, RED metric count.
  - **Feedback-loop evidence** — `pkyc_review` count, threshold
    `tuning_run` count, narrative action mix, STR escalation count.
  Every payload also carries an `audit_trail_anchor` block
  (spec_content_hash + decisions_hash + as_of + run_dir) so an
  examiner can independently verify nothing was rewritten between
  the run and the pack. Also ships `render_effectiveness_markdown()`
  which produces a one-page board-ready Markdown rendering with
  ✅/⚠️/❌ icons per finding. Same determinism contract as
  `goaml_xml.py`/`amla_str.py` — same inputs → same JSON bytes.
  CLI:
  ```
  aml effectiveness-pack examples/canadian_schedule_i_bank/aml.yaml \
    --out pack.json --markdown-out pack.md
  ```
  25 new tests cover schema envelope, byte-determinism, gap/satisfied/
  warning status routing, priority bucketing, FP proxy math, narrative
  acceptance rate, tuning-run satisfied-vs-warning logic, RED-metric
  counting, Markdown rendering of pillars + audit anchor, end-to-end
  run-dir round-trip against the bundled CA spec, and Pydantic enum
  validation on the new field.
- **Tuning Lab Streamlit page** (`dashboard/pages/23_Tuning_Lab.py` +
  `dashboard/tuning_state.py`): UI surface for `aml tune` (PR #50). MLRO
  picks a tunable rule, optionally uploads a labels CSV
  (`customer_id,is_true_positive`) for precision/recall scoring, and
  the page renders the per-scenario table + a precision/recall scatter
  (Plotly bubble chart sized by alert count, coloured by F1) when
  labels are present. Best-F1 scenario gets called out automatically.
  The "promote a scenario" panel renders a YAML spec patch (rule
  fragment with patched fields only) the operator can download and
  merge into `aml.yaml` to promote the candidate threshold; a
  `# Spec patch produced by the Tuning Lab` header reminds the user
  to re-run `aml validate` after merging. The page also writes a
  `tuning_run` event to the current session's run dir whenever a
  sweep is executed (toggle in the sidebar) — every threshold
  consideration is part of the audit trail. Page mapped into
  `audience.py` for `vp`, `director`, `manager`, `pm` personas. Round-4
  PR #1 — closes the "no UI for the new CLI" gap that PR #47 closed
  for narratives + pkyc. 15 new tests under `TestParseLabelsCSV`,
  `TestRulesWithTuningGrid`, `TestScenariosToTable`, `TestBestScenario`,
  `TestRenderSpecPatch`, and `TestEndToEnd` cover label parsing
  (truthy/falsy variants, missing column, empty rows), tunable-rule
  filtering, table flattening with and without metric columns, best-by
  metric ranking, YAML round-trip of the spec patch, and an
  end-to-end sweep → table → patch composition against the bundled
  Canadian Schedule I example. None of them import streamlit.
- **Tuning Lab — threshold sweep with shadow diff + precision/recall**
  (`engine/tuning.py`, `cli.py:tune`, `Rule.tuning_grid` spec field).
  Closes Round-3 plan (4 of 4 PRs shipped). Operators tune AML rule
  thresholds today by guesswork plus quarterly reviews; the Tuning
  Lab makes it cheap and defensible. Declare a `tuning_grid` on a
  rule (additive, optional spec field — engine ignores it at runtime,
  no breaking change), then `aml tune SPEC --rule RULE_ID` sweeps
  every parameter combination over a fixed dataset and reports
  per-scenario alert-count delta vs the production thresholds plus
  added/removed customer-id sets (shadow diff). When the operator
  passes `--labels labels.csv` (columns `customer_id,is_true_positive`)
  every scenario also gets precision / recall / F1 scored against the
  labels and the CLI surfaces the best-F1 scenario.
  Same dataset + same seed across the grid → apples-to-apples — the
  determinism contract that backs `test_run_is_reproducible` extends
  to the sweep. The audit ledger gets a new `Event.TUNING_RUN` event
  appended to the target run's `decisions.jsonl` (when
  `--audit-run-dir` is passed) so any threshold change has a
  documented decision trail. Internal mechanics: clones the rule
  via Pydantic `model_copy(update=...)` with deep-copied dict patches
  (no mutation of the source spec); reuses the engine's `_execute_*`
  helpers so any new rule logic type added to the engine works in
  the tuner without changes here. CLI:
  ```
  aml tune examples/canadian_schedule_i_bank/aml.yaml \
    --rule structuring_cash_deposits \
    --labels labels.csv --out tuning.json \
    --audit-run-dir .artifacts/run-20260427T141428Z
  ```
  The Canadian Schedule I example spec now ships with a `tuning_grid`
  on the `structuring_cash_deposits` rule (count × sum_amount sweep)
  so `make demo` can show the feature without spec edits. 25 new
  tests under `TestGridCombinations`, `TestSetByPath`, `TestMetrics`,
  `TestSweepRule`, `TestAuditIntegration`, `TestTuningRun`, and
  `TestSpecDeclaredGrid` cover Cartesian expansion, deep-path
  patching against a frozen rule, original-spec immutability,
  precision/recall/F1 edge cases (no predictions, no positives,
  no labels), baseline alignment with `run_spec`, monotonic
  alert-count vs threshold, audit-event emission, and end-to-end
  spec-declared grid with synthetic data.
- **Network-pattern alert explainability** (`engine/explain.py`,
  runner subgraph capture, queue page integration). Each
  `network_pattern` alert now carries the actual matched
  subgraph in `alert["subgraph"]`: nodes (with hop distance from
  the seed), undirected edges (with linking attribute + weight),
  and a SHA-256 `topology_hash` that's identical for two alerts
  on the same shape of subgraph (cluster key for duplicate
  detections — analysts can collapse 50 customers caught in one
  ring instead of triaging each independently). The new
  `engine/explain.py` provides `explain_network_alert(alert) →
  ExplainPayload` (pure function, no IO) plus `to_mermaid(payload)`
  for dashboard rendering. The Analyst Review Queue page (PR #47)
  now renders the matched subgraph as a Mermaid graph for any
  network_pattern case, with a one-line summary
  (`Pattern 'component_size' fired on C0001: 3 entity(ies)
  reachable within 2 hop(s), 2 unique counterpart(ies). Linking
  attributes: device_id×1, phone×1.`) and the topology hash
  prefix as an audit anchor. Round-3 PR #4 of 4 — the **dark-horse
  winner** of the Round-3 research scan: graph alerts are
  notoriously hard to defend in front of regulators
  ("the recursive CTE matched a 4-hop ring"); shipping this gives
  the framework an answer to "how is this not a black box?" that
  no other open-source AML project has. The runner enrichment is
  backward-compatible: alerts now carry an extra `subgraph` field
  but the existing 5 `TestNetworkPattern` tests still pass
  unchanged. 20 new tests under `TestExplainNetworkAlert`,
  `TestToMermaid`, `TestExplainPayloadModel`,
  `TestRunnerSubgraphCapture`, `TestDecimalHandling` cover happy
  path / missing subgraph raise / Mermaid escaping / render cap /
  seed fallback / triangle component round-trip / topology hash
  determinism across seeds in the same component / DuckDB Decimal
  coercion.
- **AMLA harmonised STR profile** (`generators/amla_str.py`,
  `cli.py:export-amla-str`): emits an AMLA RTS-aligned JSON
  payload from a finalised run directory. The EU's Anti-Money
  Laundering Authority (AMLA) is finalising a single harmonised
  SAR/STR template across the bloc — the Regulatory Technical
  Standards (RTS) for the SAR template have a delivery deadline
  of **2026-07-10**. This generator targets the February 2026
  consultation draft so EU obliged entities have a day-zero
  adapter the moment the RTS ratifies. Maps the framework's
  primitives to AMLA fields: `rule_id` + `tags` →
  `amla_typology_codes` (Annex II placeholder set: STR-001
  Structuring … STR-008 Virtual Asset Layering),
  `regulation_refs` → `indicators[].source_regulation`,
  customer → `subject` (natural_person vs legal_entity branch
  with optional `lei` + `beneficial_owner_chain`),
  cross-border counterparty → `cross_border_indicator`. Every
  payload carries a prominent `_draft_warning` field plus a
  `conformance` block listing which AMLA-mandatory fields the
  spec successfully populated and which need analyst fill-in
  (so auditors get one-shot view of what's automated vs manual).
  Same determinism contract as `goaml_xml.py` — same inputs +
  same `submission_date` → identical JSON bytes. CLI:
  ```
  aml export-amla-str spec.yaml --lei 529900T8BM49AURSDO55 \
    --sector CREDIT_INSTITUTION --out amla_str.json
  ```
  Round-3 PR #2 of 4. Sources for the RTS draft cited in
  module docstring; 26 new tests under `TestTypologyMapping`,
  `TestBuildReport`, `TestPayload`, and `TestRunDirRoundTrip`
  cover typology hint matching, natural-person vs legal-entity
  subject branches, beneficial-ownership pass-through, cross-
  border indicator computation, draft-warning emission,
  conformance counting (populated vs unmapped), byte-determinism,
  and end-to-end payload generation against the EU bank + crypto
  VASP example specs.
- **Analyst Review Queue dashboard page**
  (`dashboard/pages/22_Analyst_Review_Queue.py` +
  `dashboard/queue_state.py`): a triage view that composes the new
  `narratives/` and `pkyc/` packages so analysts can review draft
  STR/SAR text + active pKYC triggers + recalculated risk ratings
  in one place — instead of reading JSON files. Per-case actions
  (Accept / Amend / Reject / Escalate-to-STR) write into the
  existing `AuditLedger` via two new event types
  (`Event.NARRATIVE_REVIEW`, `Event.PKYC_REVIEW`); the append-only
  hash chain means every queue action is permanently part of the
  run's audit trail. Filtering by severity, "only with pKYC
  triggers", and "only with rating changes" keeps the page
  responsive for large case loads (50-row render cap with
  filter-to-narrow guidance). Page is mapped into `audience.py`
  for `analyst` and `manager` personas. Round-3 PR #1 of 4 — closes
  the "no UI surface" gap that made PR #45 + PR #46 feel half-shipped.
  18 new tests under `TestBuildQueueRows`, `TestActionMapping`,
  `TestRecordDecision`, `TestAuditChainIntegration`, and
  `TestEndToEndWithRealRun` cover queue composition, narrative
  attachment, country-risk + pattern trigger routing, rating-change
  detection, audit-ledger hash-chain integration, and a
  finalised-run round-trip — none of them import streamlit.
- **pKYC trigger engine** (`pkyc/` package): Perpetual Know Your
  Customer — events trigger re-review instead of the calendar.
  Five built-in detectors: `SanctionsHitDetector` (consumes
  `SyncResult.added` from PR #44 — only newly-added sanctions
  entries fire, since pre-existing entries were already screened
  at onboarding), `AdverseMediaDetector`, `CountryRiskDetector`
  (FATF black/grey lists), `TransactionPatternDetector` (alert
  count over lookback window crosses threshold), `StaleKYCDetector`
  (calendar fallback with risk-rating-keyed thresholds: critical
  180d, high 365d, medium 730d, low 1095d). Each detector is **pure**
  — same `ScanContext` in → same triggers out — so callers can A/B
  detector configurations without surprise. The `RiskRecalculator`
  composes triggers into a new rating (one critical → critical;
  ≥1 high → bump one rung capped at high; ≥2 mediums → bump one
  rung) so every escalation has an auditable trigger trail. The
  scan engine is side-effect free: it returns a `TriggerScan` with
  `triggers` + `rating_changes`; the caller decides whether to
  persist back to source. CLI:
  ```
  aml pkyc-scan SPEC --high-risk-countries RU,KP,IR \
    --sanctions-added-file ofac-delta.json \
    --alert-threshold 3
  ```
  Composes with PR #44 (sanctions feeds): when a daily
  `sanctions-sync` produces a `SyncResult` with new entries, feed
  it into `pkyc-scan` and any of your customers matching a brand-new
  designation gets flagged for escalation **on the same business day**
  — no waiting for the next calendar review. 37 new tests cover
  trigger model validation, each detector's match logic +
  case-insensitive matching + duplicate-name handling + severity
  override, recalculator escalation ladder + rung-capping, scan
  aggregation, JSON serialisation round-trip, custom-detector
  selection, and end-to-end composition with the sanctions package
  cache.
- **Narrative drafter with pluggable LLM backends** (`narratives/`
  package): structured STR/SAR drafting with three backends in v1 —
  `TemplateBackend` (deterministic, dependency-free, default;
  wraps the existing `generators/narrative.py` text), `OllamaBackend`
  (local-first, calls a running Ollama server with `format=json` so
  PII never leaves the host), and `OpenAIBackend` (opt-in, requires
  `OPENAI_API_KEY`, refuses to instantiate without it). All backends
  produce a `DraftedNarrative` Pydantic model with structured fields:
  `narrative_text`, `key_findings`, `citations` (each tagged with
  `rule_id` so analysts can verify the citation links back to a
  regulation reference the rule actually declared — not text the
  model invented), `recommended_action`
  (`file_str|close_no_action|investigate_further`), and `confidence`
  ∈ [0,1]. The Ollama prompt explicitly instructs the model to
  cite **only** from the provided regulation_refs; hallucinated
  citations are the worst failure mode for a regulator-facing
  artifact. Backend HTTP IO is isolated to a single `_call_*`
  function per backend so unit tests patch one symbol and run
  network-free. Failures (server down, malformed JSON, schema
  mismatch) raise `NarrativeError` so callers can decide between
  fallback to template or surfacing to the analyst. CLI:
  ```
  aml draft-narrative SPEC CASE_ID --backend template|ollama|openai
  ```
  29 new tests cover model validation (`extra="forbid"`, frozen,
  confidence range, action enum), template determinism + severity
  routing, mocked Ollama happy-path / non-JSON / empty / schema
  violations, OpenAI key gating + happy path, factory dispatch, and
  run-dir round-trip with txn-window filtering.
- **Sanctions feed adapters** (`sanctions/` package): pluggable
  upstream-feed parsers + content cache that keep `data/lists/*.csv`
  fresh without operator scripting. Three adapters ship in v1:
  `OFACAdvancedXMLSource` (OFAC SDN Advanced XML),
  `EUConsolidatedSource` (EU FSF consolidated XML), and
  `ComplyAdvantageWebhookSource` (ComplyAdvantage Monitor webhook
  payloads, with HMAC-SHA256 signature verification — no live API
  call, since the webhook delivery model is push-based). Each adapter
  splits cleanly into `fetch(url) → bytes` (only IO surface) and
  `parse(payload) → list[SanctionEntry]` so unit tests run
  network-free. `SanctionsCache` writes a canonical CSV
  (rows sorted) and a sidecar `.cache/<name>.meta.json` with
  SHA-256 + row count + fetched_at; re-syncing the same payload is a
  no-op (`unchanged=True`). Otherwise `SyncResult` reports `added` /
  `removed` deltas vs the previous on-disk content so operators can
  preview before merging into production lists. CLI:
  ```
  aml sanctions-sync ofac --from-file sdn_advanced.xml
  aml sanctions-sync eu  --from-file euConsol.xml
  ```
  Closes the loop with `list_match` rules — refreshed CSV is consumed
  by the engine on next run with no spec change. 31 new tests under
  `TestOFACParser`, `TestEUParser`, `TestComplyAdvantageParser`,
  `TestSanctionsCache`, `TestSyncOrchestrator`,
  `TestCSVCompatibleWithEngine` cover XML parsing, party-type
  mapping, country precedence, alias collection, JSON parsing, HMAC
  verify accept/reject paths, idempotent re-pull, delta-diff, and
  engine-loader compatibility.
- **goAML 5.0.2 XML exporter** (`generators/goaml_xml.py`,
  `cli.py:export-goaml`): emit UNODC-format STR/SAR XML from a finalised
  run directory. One `<report>` per case, batched under a `<reports>`
  root. Maps the framework's primitives to goAML in the obvious way:
  `rule_id` → `<report_indicators>/<indicator>`, `regulation_refs` →
  `<reason>`, `customer` → `<t_person>` under `<t_from_my_client>`,
  transactions in the alert window → `<transaction>`, channel → goAML
  funds code (cash/wire/crypto → K/A/X). Currency is auto-derived from
  `program.jurisdiction` (CA→CAD, US→USD, EU→EUR, UK→GBP). Output is
  byte-deterministic for fixed inputs — cases sort by `(rule_id,
  case_id)`; transactions sort by `(booked_at, txn_id)` — so the same
  spec + same run + same `submission_date` produces identical XML
  bytes. CLI:
  ```
  aml export-goaml examples/canadian_schedule_i_bank/aml.yaml \
    --out goaml.xml --report-code STR --rentity-id 12345
  ```
  goAML is the de-facto FIU reporting standard accepted by 60+ FIUs;
  the EU AMLA ITS draft (due July 2026) extends this same schema, so
  AMLA-specific fields will land as deltas on this exporter rather than
  as a rewrite. PII is never persisted in the audit ledger — the
  exporter re-resolves customer + txn data through the spec's data
  source at export time. 14 new tests under `TestGoAMLExporter` cover
  root shape, header fields, currency-by-jurisdiction, transaction
  filtering by customer + window, indicator/tag emission, regulation
  reference inclusion, byte-determinism, run-dir round-trip, missing
  `cases/` raises, funds-code mapping, and `additional_info` content.
- **`rule.evaluation_mode` field** (`spec/models.py`,
  `schema/aml-spec.schema.json`): each rule can now declare
  `batch | streaming | both` (default `batch`). v1 engine still executes
  batch only — the field is metadata that records institution intent so an
  operator can route to a streaming runner at deployment time. Lays
  groundwork for the Kafka/Kinesis evaluator (research scan #2). 5 new
  tests under `TestEvaluationMode` confirm default, accepted values,
  rejected invalid value, and that setting `streaming` does not change
  the run output (back-compat invariant).
- **Crypto VASP example spec** (`examples/crypto_vasp/aml.yaml`): minimal AML
  spec for a Virtual Asset Service Provider. Demonstrates the framework's
  crypto coverage with four rules: stablecoin layering velocity (48h
  window, $20k aggregate), sanctioned-wallet screening (`list_match` against
  bundled `sanctioned_wallets.csv`), nested-wallet ring detection
  (`network_pattern` over `resolved_entity_link`), and a single-day swap
  threshold mirroring LVCTR. Built around TRM Labs' 2026 Crypto Crime
  Report finding that stablecoins were ~84% of fraud-scheme inflows in
  2025 with hold times collapsing under 48h. 3 new tests under
  `TestCryptoVASPSpec` lock the spec shape and bundled wallet list.
- **Entity-resolution layer** (`engine/entity_resolution.py`): runtime
  builds a `resolved_entity` view + `resolved_entity_link` table inside
  the engine's DuckDB. Linking attributes (`phone`, `email`, `device_id`,
  `address`, `tax_id`, `wallet_address`) are recognized when present on
  the customer contract — pairs of customers sharing a non-null value
  appear as edges with attribute + weight. v1 uses customer_id as the
  resolved entity; the table is the substrate for the upcoming
  `network_pattern` rule type. Wired into the runner so every spec gets it
  for free; no spec changes required. Production deployments swap in a
  real ER service (Senzing, Quantexa) by overriding `resolve_entities`.
- 5 new tests under `TestEntityResolution` cover: empty-spec stub, shared
  phone, shared device_id, NULL-doesn't-link semantics, view shape.
- **`network_pattern` rule type** (`engine/runner.py`, `spec/models.py`,
  `schema/aml-spec.schema.json`): 5th rule logic type. Walks the
  entity-resolution graph (`resolved_entity_link`) via DuckDB recursive
  CTE up to `max_hops` away from each customer and flags those whose
  ego-network satisfies a `having` clause. Two patterns supported in v1:
  `component_size` (mule herd / nested-account ring) and
  `counterparty_count` (hub-and-spoke / synthetic-identity rings).
  Spec example:
  ```yaml
  logic:
    type: network_pattern
    pattern: component_size
    max_hops: 2
    having: { component_size: { gte: 3 } }
  ```
- 5 new tests under `TestNetworkPattern` cover three-customer ring,
  isolated customer non-fire, two-customer pair, no-links, and
  hub-and-spoke counterparty-count pattern.

### Security
- **Cross-tenant API isolation** (`api/db.py`, `api/main.py`): every read
  endpoint now scopes by the JWT's `tenant` claim. `list_runs`, `get_run`,
  `get_run_alerts`, `get_run_metrics`, `get_reports`, `get_alerts_cef`
  accept an optional `tenant_id` and filter (or JOIN through `runs`) on
  it. `store_run` persists the tenant. The Postgres schema gains a
  `tenant_id TEXT` column to match SQLite. Tokens were tenant-aware at
  issuance but not enforcement; this closes that gap.
- 3 new tests under `TestTenantIsolation` confirm `bank_a` can't list,
  get, or read alerts for `bank_b`'s runs.
- **Webhook HMAC signing** (`api/main.py`): `WebhookConfig.secret` is now an
  optional field. When provided at registration, the dispatch path computes
  `HMAC-SHA256(secret, body)` and sends it as `X-AML-Signature: sha256=<hex>`
  alongside the JSON payload. Receivers verify by recomputing the HMAC over
  the raw body and comparing constant-time. Same wire convention as Stripe /
  GitHub webhooks. Hooks without a secret continue to work unsigned.
- 4 new tests under `TestWebhookSigning` cover registration response
  shape, the `_sign_webhook` helper matching stdlib `hmac`, and the
  signature header being set on outgoing requests.
- **Audit-ledger snapshot is read-only after finalize** (`engine/audit.py`):
  `manifest.json`, `input_manifest.json`, `spec_snapshot.yaml`,
  `alerts/*.jsonl`, `alerts/*.hash`, and `rules/*.sql` are `chmod 0o444`-ed
  once the runner finishes writing. Accidental rewrites and most malicious
  processes (running as the engine user) now fail loudly. `decisions.jsonl`
  is intentionally left writable so dashboard human decisions can append.
  No-op on Windows (uses ACLs differently). Documented as advisory — for
  real WORM, point `artifacts_root` at a hardware-WORM mount.
- 4 new tests under `TestAuditLedgerFrozen` confirm the snapshot is
  read-only, that direct writes raise `PermissionError`, and that
  `decisions.jsonl` stays append-capable.

### Tests
- **`TestWindowDST` documents engine timezone semantics**: `parse_window` is
  calendar-blind by design; `as_of` and `booked_at` are naive datetimes in
  the same timezone (UTC by convention). Three new tests assert the
  invariants — `parse_window("24h") == parse_window("1d")`,
  `parse_window` is idempotent, and a 24h-window rule still aggregates
  correctly across the US spring-forward DST instant. Closes the quality
  review's flagged untested area.

### Refactor
- **Dashboard pages now use `Event` / `Queue` constants** (`pages/3_Alert_Queue.py`,
  `pages/4_Case_Investigation.py`): the bulk-action and per-case action
  buttons that write to `decisions.jsonl` (and the `isin([...])` filters that
  drive the open-case view) reference the `engine.constants` enums instead
  of inline string literals. Closes the original review's smell about
  audit-log strings drifting between the engine and UI writers.
- **`paths.py` — single source for `PROJECT_ROOT`, `PACKAGE_ROOT`,
  `SCHEMA_PATH`, `REFERENCE_LISTS_DIR`.** `Path(__file__).resolve().parents[3]`
  was repeated in `spec/loader.py`, `dashboard/state.py`, and
  `api/main.py` with a brittle index that breaks if the package gets
  nested deeper. `engine/runner.py:_load_reference_list` carried its own
  `parents[1]` for `data/lists`. All four now import from one module.
- **`engine/constants.py` — single source of truth for event + queue names.**
  String literals like `"case_opened"`, `"escalated_to_str"`,
  `"closed_no_action"` were duplicated across `runner.py`, dashboard pages,
  and metrics dispatch. They're now `Event.CASE_OPENED`, `Queue.STR_FILING`,
  etc. Decisions written to the audit log are forever — a typo in one place
  used to silently drift; importing the constant now catches the change at
  type-check time.
- 3 new tests under `TestEngineConstants` freeze the literal values (so
  renames are explicit decisions, not silent breaks of past audit logs)
  and confirm a real run emits the canonical strings.

### Refactor (later)
- **`api/db.py` Postgres/SQLite dedup**: `_with_conn()` context manager
  yields a thin wrapper that translates `?` placeholders to `%s` for
  psycopg2 on the fly. Each public CRUD function now writes its query
  once instead of carrying two near-identical SQL bodies. ~50 LOC removed.
  No public API changes; existing Postgres mock tests pass unchanged.
- **`data/synthetic.py` `_make_txn` helper**: extracted from eight near-
  identical planted-positive blocks. Each used to be 7-8 lines of dict
  literal repeating the same keys (`txn_id`, `customer_id`, `amount`,
  `currency`, `channel`, `direction`, `booked_at`); call sites are now a
  single `_make_txn(tid, customer, amount, booked_at, channel=..., ...)`
  invocation. Output is byte-identical — the existing
  `test_run_is_reproducible` test verifies this.

### Changed
- **`list_match` fuzzy matcher upgrade** (`engine/runner.py`): the previous
  token-overlap matcher missed common sanctions-screening edge cases —
  diacritics (`Müller` vs `Mueller`), edit-distance differences (`VOLKOV`
  vs `VOLKOVA`, `JON` vs `JOHN`), and substring suffixes. The new matcher
  ASCII-folds accents via `unicodedata.NFKD`, scores each entry by
  `max(token_overlap, SequenceMatcher.ratio)`, and returns the
  highest-scoring match above threshold. No new dependency — pure stdlib.
- 9 new tests under `TestFuzzyMatcher` cover accents, typos, suffixes,
  transposed tokens, the genuinely-different-name negative case, and the
  best-of-many tie-break.
- **`python_ref` error boundary** (`engine/runner.py`): a scorer that raises
  (missing module, missing attribute, runtime exception inside the model)
  no longer aborts the whole run mid-write. The engine logs the exception,
  records zero alerts for that rule, appends a `rule_failed` decision event
  with the error class + message, and continues with the remaining rules.
  The audit ledger now reflects which rules failed instead of being left
  partially written. Spec-level violations (allow-list miss) still raise —
  those indicate a bad spec, not a runtime fault.
- **Rate-limiter eviction + Retry-After** (`api/main.py`): the in-memory
  `_request_counts` dict no longer grows unbounded under IP-rotation
  attacks — empty windows are deleted, and a global cap (configurable via
  `API_RATE_LIMIT_MAX_IPS`, default 10000) evicts the IPs with the oldest
  activity when exceeded. 429 responses now include a `Retry-After`
  header pointing to when the oldest tracked request leaves the window.

### Refactor
- **`metrics/engine._compute_sql_proxy` split** — the 110-line keyword-dispatch
  is now six named handler functions (`_proxy_repeat_alert`,
  `_proxy_filing_latency`, `_proxy_lctr_completeness`, `_proxy_edd_review`,
  `_proxy_sla_compliance`, `_proxy_avg_resolution`) routed by a small
  `_PROXY_DISPATCH` table. Each handler is independently readable and
  reviewable. The dispatch table preserves the original first-match-wins
  ordering so behaviour is unchanged.
- Extract `_resolve_run_dir` in `cli.py` — the "default to latest run-* under
  artifacts" block was duplicated in `report`, `export`, and `export-alerts`.
- Dashboard `Rule_Tuning` page now calls `engine.runner._build_warehouse`
  twice instead of re-implementing the DDL+insert loop inline. Removes ~50
  lines and an unintentional closure-over-`dtype` in the sensitivity loop
  (the second copy referenced `dtype` from outer scope, which would crash
  if every contract had `rows = []`).

### Tests
- **`TestThresholdBoundaries`** in `test_engine.py` adds nine just-below-
  threshold cases for the Canadian Schedule I spec: structuring (count<3,
  sum<20k, amounts outside the [5k–9999] filter), large_cash_lctr
  (sum<10k), and high_risk_jurisdiction (safe country, sum<5k). Three
  positive controls confirm the rules still fire when thresholds are met.
  False-positive containment is now exercised, not just coverage %.

### Security
- **Webhook SSRF blocked** (`api/main.py`): `_validate_webhook_url` resolves
  every registered URL and rejects private (RFC 1918), loopback, link-local
  (169.254/16, including the 169.254.169.254 cloud-metadata endpoint),
  multicast, and reserved addresses. Re-validates at fire time so DNS
  rebinding between registration and dispatch is contained. Bypass with
  `WEBHOOK_ALLOW_PRIVATE=1` for local dev.
- **DuckDB lockdown** (`engine/runner.py:_harden_duckdb`): every engine
  connection sets `enable_external_access=false`,
  `autoload_known_extensions=false`, `autoinstall_known_extensions=false`,
  `allow_unsigned_extensions=false`. A malicious `custom_sql` rule can no
  longer `INSTALL httpfs`, `ATTACH 'http://...'`, or `COPY TO '/tmp/exfil'`.
- **`python_ref` module allow-list** (`engine/runner.py`): callables must live
  under `aml_framework.models.` by default; `AML_PYTHON_REF_PREFIX` extends
  the list (comma-separated) for institution-specific scorer packages. A
  spec with `callable: os:getcwd` is now rejected before import.
- **JWT_SECRET hardening** (`api/auth.py`): refuse to import when the env var is
  set but shorter than 32 bytes; when unset, log a warning and use a per-process
  random secret (tokens do not survive a restart). Removes the hardcoded
  `aml-framework-dev-secret` fallback that previously let anyone with repo
  access forge tokens against a misconfigured deployment.
- **Path traversal** (`api/main.py`): `_safe_spec_path` resolves and verifies
  every API-supplied `spec_path` is inside the project root. `POST /runs`,
  `POST /validate`, and any future spec-loading endpoint reject `..`, absolute
  paths, and out-of-tree resolutions with `400`.
- **Validate endpoint info leak** (`api/main.py`): `POST /validate` no longer
  echoes the raw parser exception. Server logs the detail; the response is a
  generic message.
- **Role enforcement** (`api/main.py`): `POST /runs` and `POST /upload` now
  require `admin`/`manager`/`analyst`. `POST /webhooks` requires `admin`.
  Auditors are confirmed read-only by tests.
- **OIDC mode disables `/login`** (`api/main.py`): when `OIDC_ISSUER_URL` is
  set, the local-login endpoint returns 404 so demo credentials cannot be used.

### Changed
- **Audit-ledger determinism** (`engine/audit.py`): engine-time decisions now
  stamp `ts` from `as_of` (or an explicit per-decision time like the simulated
  resolution time) instead of wall-clock `datetime.now()`. The hash chain over
  `decisions.jsonl` is now reproducible — re-running with the same spec, data,
  and `as_of` produces an identical `decisions_hash`.
- **`AuditLedger.append_to_run_dir`** is the single canonical entry point for
  human-time decision writes. Both dashboard pages (`Alert_Queue`,
  `Case_Investigation`) now route through it instead of opening
  `decisions.jsonl` directly with drifted shapes.
- **`AuditLedger.verify_decisions`** accepts an optional `expected_hash` for
  out-of-band tamper detection. The default behaviour (read the hash from the
  same `manifest.json` that lives next to `decisions.jsonl`) is documented as
  weaker, with the recommended path explicitly called out.

### Tests
- `test_run_is_reproducible` now asserts equality of `decisions_hash`,
  `spec_content_hash`, and the full `inputs` manifest across re-runs.
- New `TestAuditLedgerDeterminism` covers `append_to_run_dir` and the
  external-hash path through `verify_decisions`.

### Documentation
- Refresh README test counts to match the 288-test suite across 9 files.
- Sync `docs/spec-reference.md` with the schema (rule `status` and `tags`,
  top-level `metrics` and `reports`).
- Add `CHANGELOG.md`, `docs/deployment.md`, `docs/api-reference.md`.
- Update repo-layout block to surface `docs/case-studies/`, `docs/pitch/`.
- README dashboard intro now says "21 purpose-built pages" (was 20).
- `CONTRIBUTING.md` checklist now requires a `CHANGELOG.md` entry per feature.

## 2026-04-26 — PR #17 (`feature/docs-screenshots-coverage`)

### Added
- Persona workflow screenshots (CCO, VP, Manager, Analyst, Auditor, Developer)
  under `docs/screenshots/workflows/`.
- README sections per persona with linked screenshots.
- Coverage tests for previously uncovered branches across the engine and API.

### Fixed
- README and CLAUDE.md page count drift (now 21 pages).

## 2026-04-25 — PR #16 (`feature/code-quality-and-new-features`)

### Added
- Refactored engine runner with `_open_cases_for_alerts` and `_finalize_run`
  helpers.
- Split dashboard `data_layer.py` (636 lines) into `maturity.py`,
  `frameworks.py`, `roadmap.py`.
- Test consolidation into 9 files: `test_api`, `test_engine`, `test_generators`,
  `test_spec`, `test_metrics`, `test_data_sources`, `test_integrations`,
  `test_performance`, `test_e2e_dashboard`.

### Fixed
- CI test references updated for consolidated test layout.
- Latin-1 encoding fallback for PDF export when reportlab is unavailable.

## 2026-04-24 — PR #15 (`feature/nice-to-haves`)

### Added
- SLA timers per case (countdown + breach detection).
- Narrative persistence on Case Investigation page.
- Data validator (`aml validate-data`) for CSV / Parquet inputs against the
  data contract.
- Case workflow polish: assigned-to filter, resolution code, soft-delete.

## 2026-04-23 — PR #14 (`feature/ux-production-readiness`)

### Added
- Docker Compose with PostgreSQL + API + Dashboard.
- API Swagger docs at `/docs`.
- One-command `make demo` target.
- Audit tamper verification (`aml verify` against decisions hash chain).
- `CONTRIBUTING.md`.

## 2026-04-22 — PRs #11–#13 (`feature/sprint-final`, `feature/final-gaps`, `feature/polish-round`)

### Added
- Spec Editor page with live YAML validation and interactive Rule Builder.
- API pagination + 600 req/min rate limiting (configurable).
- SSO/OIDC stub for downstream IdP integration.
- Adverse media screening rule template.
- OpenTelemetry instrumentation stub.
- Alert acknowledge / snooze actions.
- Typology Catalogue page (20+ template rules across 9 categories).
- Comparative Analytics page (run-over-run trend view).
- Email digest CLI for scheduled exports.

## 2026-04-21 — PRs #9–#10 (`feature/final-roadmap-items`, `feature/next-sprint`)

### Added
- UK / FCA spec (`examples/uk_bank/aml.yaml`) — POCA 2002, OFSI sanctions.
- S3 and GCS data source loaders.
- Audit ledger tamper detection (`AuditLedger.verify_decisions`).
- Customer 360 page.
- EU / AMLD6 spec (`examples/eu_bank/aml.yaml`) with PEP screening.
- Role-based page visibility via audience selector.
- Scheduled run runner (`aml schedule`).

## 2026-04-20 — PR #8 (`feature/complete-roadmap`)

### Added
- Helm chart for Kubernetes deployment (`deploy/helm/`).
- XGBoost scorer reference for `python_ref` rules.
- Snowflake / BigQuery warehouse connectors.
- Multi-tenant scaffolding and load tests.
- Coverage push to 99 % with 206 tests.

## 2026-04-19 — PR #7 (CI verification)

### Fixed
- CI: auto-format on push, Dockerfile build, Playwright stability.
- CI: `httpx` added to API extras (FastAPI TestClient requirement).
- CI: skip OIDC / RBAC tests when `jwt` is not installed.

## 2026-04-18 — initial AML framework merge

### Added
- Spec layer (`schema/aml-spec.schema.json`, `src/aml_framework/spec/`).
- Engine on DuckDB with 4 rule types: `aggregation_window`, `custom_sql`,
  `list_match`, `python_ref`.
- Generators: SQL, DAG stubs, control matrix, STR narratives.
- Metrics engine with RAG bands and audience-routed reports.
- 21-page Streamlit dashboard.
- FastAPI REST layer with JWT auth.
- Audit ledger with SHA-256 hash chain.
- Synthetic data generator with planted positives (C0001–C0009).
- TD Bank 2024 case study (`docs/case-studies/td-2024.md`).
- Five example specs across US, CA, EU, UK jurisdictions.
