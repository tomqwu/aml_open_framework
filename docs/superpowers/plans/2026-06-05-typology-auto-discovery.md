# Typology Auto-Discovery → Candidate-Rule Pipeline — Plan (#496)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Fresh implementer per task + two-stage review. Steps use `- [ ]`.

**Goal:** An OFFLINE, deterministic `aml discover-typologies` that clusters a run's UNEXPLAINED activity (customers not caught by any rule) into candidate typologies and emits a `candidate_typologies.yaml` of proposed rule stubs (status `pending_promotion`) that flow through the existing `aml typology-import` → validate → approval path. Closes #496.

**Architecture:** Pure-stdlib, deterministic builder `engine/typology_discovery.py` (no sklearn — clustering is a fixed shape signature, like `engine/equivalence_clustering.py`; runs OFFLINE via CLI, NEVER in the deterministic engine run path). A CLI command loads the spec's data the way `aml run` does, computes simple per-customer features (stdlib aggregation), filters to customers absent from the run's alerts, z-scores them across the unexplained population, clusters high-anomaly customers by which features are anomalous (the "shape"), and emits one candidate rule stub per cohort (mirroring `generators/legacy_import.build_spec_skeleton`). **Governance:** candidates are PROPOSALS (`pending_promotion`) — nothing auto-promotes to a live rule; the human runs `aml typology-import`/edits the spec.

**Tech Stack:** Python 3.10+, pydantic v2 (frozen, extra="forbid"), stdlib only (statistics, csv); typer CLI; reuses the engine's data loaders + `generators/legacy_import` stub idiom.

**Locked decisions:** offline CLI (not in the run path); deterministic stdlib z-score + shape-signature clustering (no sklearn/random); proposals only (pending_promotion, human-gated); MVP features = per-customer {txn_count, sum_amount, unique_counterparties, cross_border_ratio} (the same simple set page 49 uses).

---

### Task 1: Engine — `discover_candidates` (pure, deterministic)

**Files:** Create `src/aml_framework/engine/typology_discovery.py`; Test `tests/test_typology_discovery.py`.

The builder is pure: it takes a list of per-customer feature dicts + the set of alerted customer_ids, and returns a frozen `DiscoveryReport`. No I/O, no clock, no random.

- [ ] Write failing tests (stdlib only):
  - empty input → no candidates;
  - customers in the alerted set are excluded (only unexplained considered);
  - a cohort of unexplained customers sharing an anomalous-feature shape → one candidate with size = cohort count, the anomalous feature(s) listed, a suggested rule stub;
  - candidates below `min_cohort_size` are dropped;
  - deterministic `model_dump()` across two calls;
  - candidates sorted by size desc then signature.
- [ ] Implement:
  - Models (frozen `_Base`): `CandidateTypology` (signature: str, anomalous_features: list[str], size: int, customer_ids: list[str], suggested_rule: dict[str,Any], label: str) and `DiscoveryReport` (candidates: list[CandidateTypology], n_unexplained: int, n_candidates: int).
  - `discover_candidates(customer_features, alerted_ids, *, anomaly_z=2.0, min_cohort_size=3) -> DiscoveryReport`:
    1. unexplained = [c for c in customer_features if c["customer_id"] not in alerted_ids].
    2. For each numeric feature, compute population mean + stdev (`statistics`); per customer the z = (x-mean)/stdev (0 when stdev==0).
    3. A customer's "shape signature" = the sorted tuple of features whose |z| >= anomaly_z, each tagged hi/lo. Customers with an empty signature (no anomalous feature) are not candidates.
    4. Group unexplained customers by signature → cohorts; drop cohorts with size < min_cohort_size.
    5. For each cohort build a `suggested_rule` stub (aggregation_window) whose `having` thresholds are the cohort's min anomalous-feature values (a safe, conservative proposal) — status `pending_promotion`, tags `["auto_discovered"]`. Deterministic id from the signature.
    6. Sort candidates by (-size, signature); return the report.
- [ ] Tests green, lint, commit `feat(engine): deterministic typology discovery builder (#496)`.

---

### Task 2: CLI — `aml discover-typologies`

**Files:** Modify `src/aml_framework/cli.py`; Test `tests/test_cli_discover_typologies.py`.

Mirror `import-legacy` (writes a candidate skeleton) + `equivalence` (takes a run dir). Reuse the engine's data load + the run's alerts.

- [ ] Add `discover_typologies_cmd(spec_path, run_dir, output=..., min_cohort_size=3, anomaly_z=2.0)`:
  - Load the spec; load its data the way `aml run` does (the data loaders the runner uses), aggregate per-customer features (stdlib: txn_count, sum_amount, unique_counterparties, cross_border_ratio) from the transaction contract.
  - Read the run's alerts (alerts/*.jsonl in run_dir) → set of alerted customer_ids.
  - Call `discover_candidates(...)`; wrap the candidates' `suggested_rule` stubs into a `candidate_typologies.yaml` document (a `candidates:` list with metadata + rule), via `yaml.safe_dump`. Mirror `legacy_import.build_spec_skeleton`'s safe-write (no write when zero candidates; atomic).
  - Print a summary table (n_unexplained, n_candidates, sizes). Governance note in the output: "proposals — review + `aml typology-import` / edit the spec; nothing auto-promotes."
- [ ] Test with `CliRunner`: a run dir + spec → command succeeds, emits valid YAML with ≥0 candidates, each `status: pending_promotion`; zero-candidate case writes nothing and exits 0 with a clear message.
- [ ] Tests green, lint, commit `feat(cli): aml discover-typologies — offline candidate proposals (#496)`.

---

### Task 3: Dashboard link + docs + tests

**Files:** Modify `pages/49_Anomaly_Discovery.py` (a short "Auto-discover typologies" note + the CLI command); docs.

- [ ] Page 49: add a small `st.info`/caption pointing operators to `aml discover-typologies <run_dir>` to turn the surfaced anomalies into reviewable candidate typologies (governance: proposals, human-gated). No heavy UI. Keep page-level explainer `collapsed=True`.
- [ ] Docs: new `docs/how-to/discover-typologies.md` (indexed in how-to/index.md) — run → `aml discover-typologies` → review `candidate_typologies.yaml` → `aml typology-import` / edit spec → validate → approval. CLAUDE.md Key Design Decision bullet (offline, deterministic, proposals-only). `docs/dashboard-tour.md` Anomaly Discovery sentence. `docs/progress.md` #496 entry (2026-06-05). README CLI list: add `aml discover-typologies`.
- [ ] Docs-coverage + CLI-coverage tests green (the new command must appear in README/getting-started/a how-to). Convention tests green. Commit `docs(discovery): how-to + CLAUDE/tour/progress/readme + page-49 link (#496)`.

---

### Task 4: Full CI gate

- [ ] `make ci-lint ci-unit ci-coverage` green; `make ci-e2e` green (page 49 still renders). Final whole-branch review → finishing-a-development-branch → PR (closes #496) → Codex → CI → merge → deploy reflex.

## Self-Review
- Spec coverage: discovery builder ✓ (T1), CLI proposal artifact ✓ (T2), dashboard link + docs ✓ (T3), gate ✓ (T4). The spec→validation→approval flow is the EXISTING `typology-import`/validate/promotion path — candidates feed it, never bypass it.
- Determinism: pure builder (stdlib stats, fixed shape signature, sorted); CLI is offline (not in the deterministic run path); no sklearn anywhere.
- Governance: proposals only (`pending_promotion`), human-gated; advisory output note; nothing auto-promotes.
- Dependency safety: engine + tests stdlib-only (runs in `.[dev]`); no sklearn/numpy/pandas in the builder or its tests.
- Type consistency: `discover_candidates(...)` + `CandidateTypology`/`DiscoveryReport` used identically across engine, CLI, tests.
