# M4 — Point-in-Time Effective-Dated Reference Joins (N3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a rule evaluate reference state (customer risk_rating, account segment) **as of the transaction date** — close the Pillar-3 SCD-2 gap — via an `effective_dated` contract declaration + an optional `aggregation_window.enrich` join whose temporal predicate the SQL generator emits automatically.

**Architecture:** `DataContract.effective_dated` (schema + Pydantic, validated) declares a contract's `valid_from`/`valid_to` columns. `aggregation_window` rules gain an optional `enrich` block naming an effective-dated contract to join on a key; the SQL generator emits `JOIN <ref> ON <key> AND <ref>.valid_from <= booked_at AND (<ref>.valid_to IS NULL OR booked_at < <ref>.valid_to)`, so the join resolves the row contemporaneous with each txn. Specs without `enrich` are byte-identical.

**Tech Stack:** Python 3.10+, Pydantic v2 (discriminated-union rule logic), DuckDB SQL generation, JSON Schema, pytest.

---

## Background facts (verified)

- `DataContract` (spec/models.py:333) has no temporal notion today. `Column` has `max_staleness_days` (freshness), not validity periods.
- Multi-contract joins exist **only** in `custom_sql` (author-written, e.g. `pep_screening`); `aggregation_window` is single-`source`, framework-generated (sql.py:154-198) and joins nothing — so the only place to *auto-emit* an as-of predicate is a new aggregation-window join clause.
- `aggregation_window` SQL today: `FROM <source> WHERE <filter> AND booked_at >= {window_start} AND booked_at < {as_of} GROUP BY <group_by> HAVING <having>` (sql.py:154-198).
- DuckDB warehouse: one table per `contract.id` from raw input rows, no SCD-2 dedup (runner.py:194). Effective-dated input simply has multiple rows per key with `valid_from`/`valid_to`.
- Pillar-3 PARTIAL evidence (dashboard/pages/43_North_Star_Coverage.py:250-286) — gap is exactly "resolve txn → contemporaneous KYC state at query time (per-txn, not run-boundary)".
- Schema: `data_contract` at schema/aml-spec.schema.json:150; `aggregation_window` logic object nearby. Both need the new fields (CLAUDE.md spec+schema-sync rule).
- Synthetic data has one row per customer (no SCD-2) — M4 tests hand-build a 2-version customer.

## File Structure

- **Modify** `src/aml_framework/spec/models.py` — `EffectiveDated` model + `DataContract.effective_dated`; `EnrichJoin` model + `AggregationWindowLogic.enrich`; cross-ref validation.
- **Modify** `schema/aml-spec.schema.json` — `effective_dated` on data_contract + `enrich` on aggregation_window.
- **Modify** `src/aml_framework/generators/sql.py` — emit the enrich JOIN + as-of predicate; allow enrich columns in filter/having/group_by.
- **Create** `tests/test_point_in_time.py` — point-in-time correctness + SQL-shape + back-compat tests.
- **Modify** `docs/spec-reference.md` (+ `CLAUDE.md` architecture note) — document the affordance.
- **Modify** `src/aml_framework/dashboard/pages/43_North_Star_Coverage.py` — flip Pillar 3 PARTIAL→COVERED with honest evidence.

## Spec shapes (the contract every task uses)

```yaml
data_contracts:
  - id: customer
    effective_dated: { valid_from: valid_from, valid_to: valid_to }   # valid_to optional/null = open
    columns: [ ..., {name: valid_from, type: timestamp}, {name: valid_to, type: timestamp, nullable: true} ]
rules:
  - id: high_risk_burst
    logic:
      type: aggregation_window
      source: txn
      window: 7d
      enrich:                          # M4: as-of join to an effective-dated contract
        contract: customer
        on: customer_id                # join key present on BOTH source + ref
        where: ["risk_rating = 'high'"] # predicates over enriched columns
      having: "COUNT(*) >= 3"
```

---

### Task 1: `EffectiveDated` on DataContract (model + schema + validation)

**Files:**
- Modify: `src/aml_framework/spec/models.py`
- Modify: `schema/aml-spec.schema.json`
- Test: `tests/test_point_in_time.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_point_in_time.py
from __future__ import annotations

import pytest

from aml_framework.spec.models import AMLSpec


def _spec_dict(**contract_extra):
    return {
        "version": "0.1",
        "program": {
            "name": "p", "jurisdiction": "US", "regulator": "FinCEN",
            "owner": "cco", "effective_date": "2026-01-01",
        },
        "data_contracts": [
            {
                "id": "customer", "source": "raw.customers",
                "columns": [
                    {"name": "customer_id", "type": "string", "nullable": False},
                    {"name": "risk_rating", "type": "string"},
                    {"name": "valid_from", "type": "timestamp", "nullable": False},
                    {"name": "valid_to", "type": "timestamp", "nullable": True},
                ],
                **contract_extra,
            },
        ],
        "rules": [],
        "queues": [{"id": "q1", "name": "Q"}],
    }


def test_effective_dated_accepts_valid_columns():
    spec = AMLSpec.model_validate(
        _spec_dict(effective_dated={"valid_from": "valid_from", "valid_to": "valid_to"})
    )
    c = spec.data_contracts[0]
    assert c.effective_dated is not None
    assert c.effective_dated.valid_from == "valid_from"
    assert c.effective_dated.valid_to == "valid_to"


def test_effective_dated_valid_to_optional():
    spec = AMLSpec.model_validate(_spec_dict(effective_dated={"valid_from": "valid_from"}))
    assert spec.data_contracts[0].effective_dated.valid_to is None


def test_effective_dated_rejects_unknown_column():
    with pytest.raises(Exception):  # cross-ref: valid_from must be a declared column
        AMLSpec.model_validate(_spec_dict(effective_dated={"valid_from": "nope"}))


def test_absent_effective_dated_is_none():
    spec = AMLSpec.model_validate(_spec_dict())
    assert spec.data_contracts[0].effective_dated is None
```

> Step 1a: confirm the minimal valid `AMLSpec` dict shape (required top-level keys, queue field names) by reading an existing model test (e.g. `tests/test_models.py`) — adjust `_spec_dict` to match before running (version key? `queues` vs `queue`? severity-less rules ok?).

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_point_in_time.py -q`
Expected: FAIL — `effective_dated` is an unknown field (extra="forbid") / attribute missing.

- [ ] **Step 3: Add the model + validator** (`spec/models.py`, near `DataContract`)

```python
class EffectiveDated(_Base):
    """SCD-2 temporal metadata: this contract carries validity-period columns
    so a rule can join it AS OF the transaction date (point-in-time), not the
    latest row. `valid_to` is optional — NULL means the row is still current."""

    valid_from: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    valid_to: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
```

Add to `DataContract`:

```python
    effective_dated: EffectiveDated | None = None
```

Add a model validator on `DataContract` (mirror existing column-cross-ref validators) that the named columns exist:

```python
    @model_validator(mode="after")
    def _check_effective_dated_columns(self) -> DataContract:
        if self.effective_dated is not None:
            names = {c.name for c in self.columns}
            ed = self.effective_dated
            missing = [c for c in (ed.valid_from, ed.valid_to) if c and c not in names]
            if missing:
                raise ValueError(
                    f"data_contract '{self.id}'.effective_dated references unknown "
                    f"column(s): {missing}"
                )
        return self
```

- [ ] **Step 4: Mirror in the JSON schema** (`schema/aml-spec.schema.json`, data_contract properties)

```json
"effective_dated": {
  "type": "object",
  "additionalProperties": false,
  "required": ["valid_from"],
  "properties": {
    "valid_from": { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
    "valid_to":   { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" }
  }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_point_in_time.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Lint + commit**

```bash
ruff check src/aml_framework/spec/models.py tests/test_point_in_time.py
git add src/aml_framework/spec/models.py schema/aml-spec.schema.json tests/test_point_in_time.py
git commit -m "feat(point-in-time): effective_dated SCD-2 declaration on data_contract"
```

---

### Task 2: `enrich` as-of join on aggregation_window (model + schema)

**Files:**
- Modify: `src/aml_framework/spec/models.py`
- Modify: `schema/aml-spec.schema.json`
- Test: `tests/test_point_in_time.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_enrich_parses_on_aggregation_window():
    from aml_framework.spec.models import AggregationWindowLogic

    logic = AggregationWindowLogic.model_validate(
        {
            "type": "aggregation_window",
            "source": "txn",
            "window": "7d",
            "enrich": {"contract": "customer", "on": "customer_id", "where": ["risk_rating = 'high'"]},
            "having": "COUNT(*) >= 3",
        }
    )
    assert logic.enrich is not None
    assert logic.enrich.contract == "customer"
    assert logic.enrich.on == "customer_id"
    assert logic.enrich.where == ["risk_rating = 'high'"]


def test_enrich_absent_is_none():
    from aml_framework.spec.models import AggregationWindowLogic

    logic = AggregationWindowLogic.model_validate(
        {"type": "aggregation_window", "source": "txn", "window": "7d"}
    )
    assert logic.enrich is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_point_in_time.py -k enrich -q`
Expected: FAIL — `enrich` is an unknown field.

- [ ] **Step 3: Add the models** (`spec/models.py`, near `AggregationWindowLogic`)

```python
class EnrichJoin(_Base):
    """As-of join from an aggregation_window rule to an effective-dated
    reference contract. The engine joins on `on` AND the reference contract's
    validity window, so each source row matches the reference row in force at
    its `booked_at`. `where` adds predicates over the joined columns."""

    contract: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    on: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    where: list[str] = Field(default_factory=list)
```

Add to `AggregationWindowLogic`:

```python
    enrich: EnrichJoin | None = None
```

- [ ] **Step 4: Mirror in JSON schema** (the `aggregation_window` logic object)

```json
"enrich": {
  "type": "object",
  "additionalProperties": false,
  "required": ["contract", "on"],
  "properties": {
    "contract": { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
    "on":       { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
    "where":    { "type": "array", "items": { "type": "string" } }
  }
}
```

- [ ] **Step 5: Cross-ref validation (the enriched contract must be effective_dated)**

Add a validator on the spec (mirror how `rule.escalate_to`/source cross-refs are checked — find the existing spec-level `model_validator` that resolves rule sources) asserting: for every `aggregation_window` rule with `enrich`, `enrich.contract` is a declared contract AND that contract `.effective_dated is not None`. (Step 5a: locate the existing rule→contract cross-ref validator and add this beside it.)

```python
# inside the spec-level after-validator that already iterates rules + contracts:
if logic.type == "aggregation_window" and getattr(logic, "enrich", None):
    ref = contracts_by_id.get(logic.enrich.contract)
    if ref is None:
        raise ValueError(f"rule '{rule.id}' enrich references unknown contract")
    if ref.effective_dated is None:
        raise ValueError(
            f"rule '{rule.id}' enriches '{ref.id}' which is not effective_dated"
        )
```

Add a test that an `enrich` against a non-effective-dated contract is rejected.

- [ ] **Step 6: Run + lint + commit**

Run: `python -m pytest tests/test_point_in_time.py -q` → PASS.
```bash
git add src/aml_framework/spec/models.py schema/aml-spec.schema.json tests/test_point_in_time.py
git commit -m "feat(point-in-time): aggregation_window.enrich as-of join declaration"
```

---

### Task 3: SQL generator emits the as-of join

**Files:**
- Modify: `src/aml_framework/generators/sql.py`
- Test: `tests/test_point_in_time.py`

> Read `compile_rule_sql` aggregation_window branch (sql.py:154-198) + how it accesses the spec's contracts (it may only get the rule + as_of today; you may need to thread `spec` or the contract's effective_dated columns into the SQL builder). Step 3a: confirm `compile_rule_sql`'s signature and whether it can see other contracts; if not, thread the enriched contract's `effective_dated` column names in.

- [ ] **Step 1: Write the failing SQL-shape test**

```python
def test_enrich_sql_emits_asof_predicate():
    from aml_framework.spec import load_spec  # build a tiny spec via a temp file
    from aml_framework.generators.sql import compile_rule_sql
    # ... load a spec whose rule has enrich on an effective_dated customer ...
    sql = compile_rule_sql(rule, as_of=AS_OF, ...)
    low = sql.lower()
    assert "join customer" in low
    assert "valid_from" in low and "booked_at" in low
    assert "valid_to is null" in low or "valid_to >" in low
```

- [ ] **Step 2: Run to verify failure** (no join emitted yet) → FAIL.

- [ ] **Step 3: Emit the join** in the aggregation_window branch:

```python
# after building the source FROM + window predicates, when logic.enrich:
ed = <enriched contract>.effective_dated
join_sql = (
    f"JOIN {enr.contract} ON {source}.{enr.on} = {enr.contract}.{enr.on}\n"
    f"    AND {enr.contract}.{ed.valid_from} <= {source}.booked_at\n"
)
if ed.valid_to:
    join_sql += (
        f"    AND ({enr.contract}.{ed.valid_to} IS NULL "
        f"OR {source}.booked_at < {enr.contract}.{ed.valid_to})\n"
    )
# enrich.where predicates AND-ed into the WHERE clause; group_by/having may
# reference the joined columns (already free-form strings).
```

Ensure the source table is aliased consistently and existing single-source rules (no enrich) emit byte-identical SQL.

- [ ] **Step 4: Run the SQL-shape test** → PASS. Run the full sql test module → PASS (back-compat).

- [ ] **Step 5: Lint + commit**

```bash
git add src/aml_framework/generators/sql.py tests/test_point_in_time.py
git commit -m "feat(point-in-time): generate as-of JOIN predicate for enrich"
```

---

### Task 4: end-to-end point-in-time correctness test

**Files:**
- Test: `tests/test_point_in_time.py`

- [ ] **Step 1: Write the end-to-end test** — a 2-version customer, a txn between the versions, assert the rule resolves the contemporaneous value:

```python
def test_point_in_time_join_resolves_contemporaneous_row(tmp_path):
    # customer C0001: risk low [2026-05-01, 2026-05-20), high [2026-05-20, NULL)
    # txn on 2026-05-10 (risk was LOW) -> rule filtering risk='high' must NOT fire
    # txn on 2026-05-25 (risk is HIGH) -> rule fires
    # Build spec (effective_dated customer + enrich rule) + data, run engine,
    # assert alert customers == {expected}. Use load_spec + run_spec with
    # CSV/dict data and a fixed as_of (2026-06-01).
    ...
    assert fired_customers_for_may10_txn == set()       # low at txn time
    assert "C0001" in fired_customers_for_may25_txn      # high at txn time
```

> Step 4a: model this test on an existing engine end-to-end test (find one that builds a tiny spec + in-memory data + calls `run_spec`, asserting on `result.alerts`). Reuse its data-injection mechanism.

- [ ] **Step 2: Run** → PASS (proves per-txn correctness — the Pillar-3 gap is closed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_point_in_time.py
git commit -m "test(point-in-time): end-to-end contemporaneous-row resolution"
```

---

### Task 5: docs + Pillar-3 flip

**Files:**
- Modify: `docs/spec-reference.md`, `CLAUDE.md`, `src/aml_framework/dashboard/pages/43_North_Star_Coverage.py`

- [ ] **Step 1: spec-reference** — document `effective_dated` on data_contract + `enrich` on aggregation_window with the YAML example above.
- [ ] **Step 2: CLAUDE.md** — one line in Architecture/Key Design Decisions: aggregation_window rules can join an effective_dated contract as-of `booked_at` (point-in-time).
- [ ] **Step 3: North-Star page** — flip Pillar 3 `status="PARTIAL"` → `"COVERED"`; update evidence: replace the "Missing: SCD-2…" bullet with "**In:** `effective_dated` contracts + `aggregation_window.enrich` resolve txn → contemporaneous reference state at the per-txn boundary (M4)." Update any roll-up counts on the page (Covered N → N+1) and the tour/North-Star coverage line if `test_dashboard_tour_coverage`/a North-Star test pins the count. (Step 3a: check `test_north_star*`/dashboard tests for a hard-pinned PARTIAL/COVERED count before flipping.)
- [ ] **Step 4:** run `python -m pytest tests/ -k "north_star or tour or docs" -q` → PASS.
- [ ] **Step 5: Commit**

```bash
git add docs/spec-reference.md CLAUDE.md src/aml_framework/dashboard/pages/43_North_Star_Coverage.py
git commit -m "docs(point-in-time): document effective_dated/enrich + flip Pillar 3 to COVERED"
```

---

### Task 6: full local gate

- [ ] **Step 1:** `python -m pytest tests/test_point_in_time.py tests/test_models.py -q` → PASS.
- [ ] **Step 2:** `ruff check src/ tests/ && ruff format --check src/ tests/` → All checks passed.
- [ ] **Step 3:** `make ci-unit` → green. (`tests/test_point_in_time.py` uses spec/engine only — `.[dev]`-safe.)
- [ ] **Step 4:** validate an example: add an `effective_dated`+`enrich` rule to a scratch spec, `aml validate` + `aml run`, eyeball that it parses + the generated SQL (`.artifacts/.../rules/<id>.sql`) contains the as-of predicate.

---

## Self-Review

**Spec coverage (issue #484 acceptance):**
- Spec affordance for effective-dated reference data (schema + models in sync) → Tasks 1 + 2. ✓
- Engine support for the as-of join (DuckDB) → Task 3 (generated JOIN predicate). ✓
- Point-in-time test (changed-after-txn attribute resolves to the on-txn value) → Task 4. ✓
- Documented spec affordance → Task 5 (spec-reference + CLAUDE.md). ✓
- Tests + progress.md; North-Star Pillar-3 PARTIAL→COVERED → Task 5. ✓

**Placeholder scan:** the SQL-shape and end-to-end tests in Tasks 3/4 carry explicit "model on existing test X" verify-first steps (3a, 4a) rather than guessing the exact `compile_rule_sql` signature / data-injection harness — these are real uncertainties flagged for resolution at implementation time, not hand-waved logic. All model/schema code is complete.

**Type consistency:** `EffectiveDated(valid_from, valid_to)`, `DataContract.effective_dated`, `EnrichJoin(contract, on, where)`, `AggregationWindowLogic.enrich` referenced identically across tasks + the generated SQL. The YAML `effective_dated: {valid_from, valid_to}` / `enrich: {contract, on, where}` shapes match the models and the schema.

## PR / wrap-up

- Codex → fix blockers → push → draft PR `Closes #484` + checklist + test plan.
- `docs/progress.md`: M4 round entry; Pillar-3 flip is a north-star milestone — call it out.
- Engine/spec change (new SQL path) — the dashboard North-Star page changed → a deploy is warranted to surface the Pillar-3 flip live; batch the deploy with M3 if both land together.
