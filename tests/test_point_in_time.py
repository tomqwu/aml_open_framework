from __future__ import annotations

import pytest

from aml_framework.spec.models import AggregationWindowLogic, DataContract


def _contract(**extra):
    return {
        "id": "customer",
        "source": "raw.customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False},
            {"name": "risk_rating", "type": "string"},
            {"name": "valid_from", "type": "timestamp", "nullable": False},
            {"name": "valid_to", "type": "timestamp", "nullable": True},
        ],
        **extra,
    }


def test_effective_dated_accepts_valid_columns():
    c = DataContract.model_validate(
        _contract(effective_dated={"valid_from": "valid_from", "valid_to": "valid_to"})
    )
    assert c.effective_dated is not None
    assert c.effective_dated.valid_from == "valid_from"
    assert c.effective_dated.valid_to == "valid_to"


def test_effective_dated_valid_to_optional():
    c = DataContract.model_validate(_contract(effective_dated={"valid_from": "valid_from"}))
    assert c.effective_dated.valid_to is None


def test_effective_dated_rejects_unknown_column():
    with pytest.raises(Exception):
        DataContract.model_validate(_contract(effective_dated={"valid_from": "nope"}))


def test_absent_effective_dated_is_none():
    assert DataContract.model_validate(_contract()).effective_dated is None


def test_enrich_parses_on_aggregation_window():
    logic = AggregationWindowLogic.model_validate(
        {
            "type": "aggregation_window",
            "source": "txn",
            "group_by": ["customer_id"],
            "window": "7d",
            "having": {"count": {"gte": 3}},
            "enrich": {
                "contract": "customer",
                "key": "customer_id",
                "where": ["customer.risk_rating = 'high'"],
            },
        }
    )
    assert logic.enrich is not None
    assert logic.enrich.contract == "customer"
    assert logic.enrich.key == "customer_id"
    assert logic.enrich.where == ["customer.risk_rating = 'high'"]


def test_enrich_absent_is_none():
    logic = AggregationWindowLogic.model_validate(
        {
            "type": "aggregation_window",
            "source": "txn",
            "group_by": ["customer_id"],
            "window": "7d",
            "having": {"count": {"gte": 3}},
        }
    )
    assert logic.enrich is None


# --- spec-level cross-ref + end-to-end (uses a temp YAML through load_spec) ---

_BASE_SPEC = """
version: 1
program:
  name: pit_bank
  jurisdiction: US
  regulator: FinCEN
  owner: chief_compliance_officer
  effective_date: 2026-01-01
data_contracts:
  - id: txn
    source: raw.transactions
    columns:
      - {{ name: txn_id,      type: string,    nullable: false }}
      - {{ name: customer_id, type: string,    nullable: false }}
      - {{ name: amount,      type: decimal,   nullable: false }}
      - {{ name: booked_at,   type: timestamp, nullable: false }}
    quality_checks:
      - {{ not_null: [txn_id, customer_id, amount, booked_at] }}
      - {{ unique: [txn_id] }}
  - id: customer
    source: raw.customers
{customer_effective}
    columns:
      - {{ name: customer_id, type: string,    nullable: false }}
      - {{ name: risk_rating, type: string,    nullable: false }}
      - {{ name: valid_from,  type: timestamp, nullable: false }}
      - {{ name: valid_to,    type: timestamp, nullable: true  }}
rules:
  - id: high_risk_burst
    name: High-risk customer burst
    severity: high
    regulation_refs:
      - {{ citation: "31 CFR 1020.320", description: "SAR" }}
    logic:
      type: aggregation_window
      source: txn
      group_by: [customer_id]
      window: 30d
      having: {{ count: {{ gte: 2 }} }}
{enrich_block}
    escalate_to: l1_queue
workflow:
  queues:
    - {{ id: l1_queue, sla: 24h }}
"""

_ENRICH = """      enrich:
        contract: customer
        key: customer_id
        where: ["customer.risk_rating = 'high'"]"""

_EFFECTIVE = "    effective_dated: { valid_from: valid_from, valid_to: valid_to }"


def _write_spec(tmp_path, *, effective: bool, enrich: bool):
    text = _BASE_SPEC.format(
        customer_effective=_EFFECTIVE if effective else "",
        enrich_block=_ENRICH if enrich else "",
    )
    p = tmp_path / "spec.yaml"
    p.write_text(text)
    return p


def test_enrich_requires_effective_dated_contract(tmp_path):
    from aml_framework.spec import load_spec

    # enrich present but customer NOT effective_dated -> rejected
    spec_path = _write_spec(tmp_path, effective=False, enrich=True)
    with pytest.raises(Exception):
        load_spec(spec_path)


def test_effective_dated_enrich_spec_loads(tmp_path):
    from aml_framework.spec import load_spec

    spec = load_spec(_write_spec(tmp_path, effective=True, enrich=True))
    rule = spec.rules[0]
    assert rule.logic.enrich.contract == "customer"
    assert spec.data_contracts[1].effective_dated is not None


def test_enrich_key_must_exist_on_both_contracts(tmp_path):
    from aml_framework.spec import load_spec

    # key 'nope' exists on neither txn nor customer -> rejected at cross-ref.
    bad = _BASE_SPEC.format(customer_effective=_EFFECTIVE, enrich_block=_ENRICH).replace(
        "key: customer_id", "key: nope"
    )
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(Exception, match="enrich key"):
        load_spec(p)


def test_enrich_key_present_on_ref_but_not_source_rejected(tmp_path):
    from aml_framework.spec import load_spec

    # 'risk_rating' is a column of customer (ref) but NOT of txn (source).
    bad = _BASE_SPEC.format(customer_effective=_EFFECTIVE, enrich_block=_ENRICH).replace(
        "key: customer_id", "key: risk_rating"
    )
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(Exception, match="source"):
        load_spec(p)


def test_enrich_sql_emits_asof_join_predicate(tmp_path):
    from datetime import datetime

    from aml_framework.generators.sql import compile_rule_sql
    from aml_framework.spec import load_spec

    spec = load_spec(_write_spec(tmp_path, effective=True, enrich=True))
    rule = spec.rules[0]
    contracts = {c.id: c for c in spec.data_contracts}
    sql = compile_rule_sql(
        rule, as_of=datetime(2026, 6, 1), source_table="txn", contracts=contracts
    )
    low = sql.lower()
    assert "join customer" in low
    assert "customer.valid_from <= src.booked_at" in low
    assert "valid_to is null" in low
    assert "src.booked_at < customer.valid_to" in low
    assert "(customer.risk_rating = 'high')" in low  # enrich.where parenthesized into the join


def test_enrich_without_contracts_raises(tmp_path):
    from datetime import datetime

    from aml_framework.generators.sql import compile_rule_sql
    from aml_framework.spec import load_spec

    spec = load_spec(_write_spec(tmp_path, effective=True, enrich=True))
    rule = spec.rules[0]
    with pytest.raises(ValueError, match="contracts"):
        compile_rule_sql(rule, as_of=datetime(2026, 6, 1), source_table="txn")


def test_no_enrich_sql_unchanged(tmp_path):
    from datetime import datetime

    from aml_framework.generators.sql import compile_rule_sql
    from aml_framework.spec import load_spec

    spec = load_spec(_write_spec(tmp_path, effective=True, enrich=False))
    rule = spec.rules[0]
    sql = compile_rule_sql(rule, as_of=datetime(2026, 6, 1), source_table="txn")
    assert "join customer" not in sql.lower()  # back-compat: no join without enrich


def test_point_in_time_join_resolves_contemporaneous_row(tmp_path):
    """The proof: C0001's risk goes low→high on 2026-06-05. A rule that fires
    on >=2 txns by a HIGH-risk customer must count ONLY the txns booked while
    the customer was high (2 of them), NOT the earlier low-risk-period txns —
    even though the customer's *latest* row is high. A latest-row join would
    count all 4 and report count=4; point-in-time reports count=2."""
    from datetime import datetime

    from aml_framework.engine.runner import run_spec
    from aml_framework.spec import load_spec

    spec_path = _write_spec(tmp_path, effective=True, enrich=True)
    spec = load_spec(spec_path)

    data = {
        "txn": [
            # C0001 — 2 txns while LOW (must be excluded), 2 while HIGH (counted)
            {
                "txn_id": "t1",
                "customer_id": "C0001",
                "amount": 100,
                "booked_at": "2026-06-01 09:00:00",
            },
            {
                "txn_id": "t2",
                "customer_id": "C0001",
                "amount": 100,
                "booked_at": "2026-06-02 09:00:00",
            },
            {
                "txn_id": "t3",
                "customer_id": "C0001",
                "amount": 100,
                "booked_at": "2026-06-10 09:00:00",
            },
            {
                "txn_id": "t4",
                "customer_id": "C0001",
                "amount": 100,
                "booked_at": "2026-06-11 09:00:00",
            },
            # C0002 — always low, 3 txns in window: must never fire
            {
                "txn_id": "t5",
                "customer_id": "C0002",
                "amount": 100,
                "booked_at": "2026-06-10 09:00:00",
            },
            {
                "txn_id": "t6",
                "customer_id": "C0002",
                "amount": 100,
                "booked_at": "2026-06-11 09:00:00",
            },
            {
                "txn_id": "t7",
                "customer_id": "C0002",
                "amount": 100,
                "booked_at": "2026-06-12 09:00:00",
            },
        ],
        "customer": [
            # SCD-2: C0001 low until 2026-06-05, high after (open-ended).
            {
                "customer_id": "C0001",
                "risk_rating": "low",
                "valid_from": "2026-01-01 00:00:00",
                "valid_to": "2026-06-05 00:00:00",
            },
            {
                "customer_id": "C0001",
                "risk_rating": "high",
                "valid_from": "2026-06-05 00:00:00",
                "valid_to": None,
            },
            {
                "customer_id": "C0002",
                "risk_rating": "low",
                "valid_from": "2026-01-01 00:00:00",
                "valid_to": None,
            },
        ],
    }

    result = run_spec(
        spec, spec_path, data, as_of=datetime(2026, 6, 30), artifacts_root=tmp_path / "art"
    )
    alerts = result.alerts["high_risk_burst"]
    fired = {a["customer_id"]: a for a in alerts}
    assert set(fired) == {"C0001"}, f"only C0001 should fire, got {set(fired)}"
    # The killer assertion: count==2 (high-period txns only), NOT 4 (latest-row).
    assert fired["C0001"]["count"] == 2
