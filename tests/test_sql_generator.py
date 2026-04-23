from datetime import datetime
from pathlib import Path

from aml_framework.generators.sql import compile_rule_sql, parse_window
from aml_framework.spec import load_spec


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def test_parse_window_days():
    td = parse_window("30d")
    assert td.days == 30


def test_compile_structuring_rule_contains_expected_predicates():
    spec = load_spec(EXAMPLE)
    rule = next(r for r in spec.rules if r.id == "structuring_cash_deposits")

    as_of = datetime(2026, 4, 23, 12, 0, 0)
    sql = compile_rule_sql(rule, as_of=as_of, source_table="txn")

    assert "channel = 'cash'" in sql
    assert "direction = 'in'" in sql
    assert "amount BETWEEN 7000 AND 9999" in sql
    assert "COUNT(*) AS count" in sql
    assert "SUM(amount) AS sum_amount" in sql
    assert "count >= 3" in sql
    assert "sum_amount >= 25000" in sql
    assert "GROUP BY customer_id" in sql
    assert "rule_id:       structuring_cash_deposits" in sql


def test_compile_is_deterministic():
    spec = load_spec(EXAMPLE)
    rule = spec.rules[0]
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    a = compile_rule_sql(rule, as_of=as_of, source_table="txn")
    b = compile_rule_sql(rule, as_of=as_of, source_table="txn")
    assert a == b
