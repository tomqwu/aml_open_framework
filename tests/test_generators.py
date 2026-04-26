"""Generator tests — SQL, control matrix, DAG, STR narrative, board PDF."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.generators.narrative import generate_str_narrative
from aml_framework.generators.sql import (
    _compile_filter,
    _compile_having,
    _sql_literal,
    compile_rule_sql,
    parse_window,
)
from aml_framework.spec import load_spec

EXAMPLE_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run_ca(tmp_path):
    spec = load_spec(EXAMPLE_CA)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return (
        spec,
        data,
        run_spec(
            spec=spec,
            spec_path=EXAMPLE_CA,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        ),
    )


# ===================================================================
# SQL compilation
# ===================================================================


class TestParseWindow:
    def test_parse_window_days(self):
        td = parse_window("30d")
        assert td.days == 30

    def test_parse_window_all_units(self):
        assert parse_window("30d").days == 30
        assert parse_window("24h").total_seconds() == 86400
        assert parse_window("60m").total_seconds() == 3600
        assert parse_window("120s").total_seconds() == 120

    def test_unsupported_window_unit(self):
        with pytest.raises(ValueError, match="unsupported"):
            parse_window("30x")


class TestCompileRuleSQL:
    def test_compile_structuring_rule_contains_expected_predicates(self):
        spec = load_spec(EXAMPLE_US)
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

    def test_compile_is_deterministic(self):
        spec = load_spec(EXAMPLE_US)
        rule = spec.rules[0]
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        a = compile_rule_sql(rule, as_of=as_of, source_table="txn")
        b = compile_rule_sql(rule, as_of=as_of, source_table="txn")
        assert a == b


class TestCompileFilter:
    def test_filter_operators(self):
        preds = _compile_filter({"amount": {"gt": 1000}})
        assert any(">" in p for p in preds)

        preds = _compile_filter({"amount": {"lt": 500}})
        assert any("<" in p for p in preds)

        preds = _compile_filter({"amount": {"ne": 0}})
        assert any("<>" in p for p in preds)

        preds = _compile_filter({"amount": {"eq": 100}})
        assert any("=" in p for p in preds)

        preds = _compile_filter({"channel": "cash"})
        assert any("cash" in p for p in preds)

    def test_filter_between(self):
        preds = _compile_filter({"amount": {"between": [100, 500]}})
        assert any("BETWEEN" in p for p in preds)

    def test_filter_in_list(self):
        preds = _compile_filter({"channel": {"in": ["cash", "wire"]}})
        assert any("IN" in p for p in preds)

    def test_filter_gte_lte(self):
        preds = _compile_filter({"amount": {"gte": 1000}})
        assert any(">=" in p for p in preds)
        preds = _compile_filter({"amount": {"lte": 5000}})
        assert any("<=" in p for p in preds)

    def test_filter_none_and_empty(self):
        assert _compile_filter(None) == []
        assert _compile_filter({}) == []

    def test_filter_unsupported_operator(self):
        with pytest.raises(ValueError, match="unsupported filter"):
            _compile_filter({"amount": {"foo": 5}})


class TestCompileHaving:
    def test_having_operators(self):
        selects, preds = _compile_having({"count": {"gte": 3}, "sum_amount": {"lte": 50000}})
        assert len(selects) == 2
        assert any(">=" in p for p in preds)
        assert any("<=" in p for p in preds)

    def test_having_gt_lt_operators(self):
        selects, preds = _compile_having({"count": {"gt": 3}})
        assert any(">" in p for p in preds)
        selects, preds = _compile_having({"count": {"lt": 10}})
        assert any("<" in p for p in preds)

    def test_having_ne_operator(self):
        selects, preds = _compile_having({"count": {"ne": 0}})
        assert any("<>" in p for p in preds)

    def test_having_non_dict_value(self):
        selects, preds = _compile_having({"count": 5})
        assert any("count" in s for s in selects)
        assert any("5" in p for p in preds)

    def test_having_unsupported_metric(self):
        with pytest.raises(ValueError, match="unsupported having"):
            _compile_having({"nonexistent_metric": {"gte": 5}})


class TestSQLLiteral:
    def test_sql_literal_types(self):
        assert _sql_literal(True) == "TRUE"
        assert _sql_literal(False) == "FALSE"
        assert _sql_literal(42) == "42"
        assert _sql_literal(None) == "NULL"
        assert _sql_literal("hello") == "'hello'"
        assert _sql_literal("it's") == "'it''s'"  # Escape single quotes.


# ===================================================================
# Control matrix
# ===================================================================


class TestControlMatrix:
    def test_renders_markdown(self):
        from aml_framework.generators.docs import render_control_matrix

        spec = load_spec(EXAMPLE_CA)
        md = render_control_matrix(spec)
        assert "Control Matrix" in md
        assert "structuring_cash_deposits" in md

    def test_contains_regulation_refs(self):
        from aml_framework.generators.docs import render_control_matrix

        spec = load_spec(EXAMPLE_CA)
        md = render_control_matrix(spec)
        assert "PCMLTFA" in md


# ===================================================================
# DAG generator
# ===================================================================


class TestDAGGenerator:
    def test_renders_dag_stub(self):
        from aml_framework.generators.dag import render_dag_stub

        spec = load_spec(EXAMPLE_CA)
        py = render_dag_stub(spec)
        assert "def" in py or "DAG" in py or "dag" in py


# ===================================================================
# STR / SAR narrative
# ===================================================================


class TestSTRNarrative:
    def test_narrative_generates(self, tmp_path):
        spec, data, result = _run_ca(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        import json

        case_files = sorted((run_dir / "cases").glob("*.json"))
        case = json.loads(case_files[0].read_bytes())
        customer_id = case.get("alert", {}).get("customer_id", "")
        customers = data.get("customer", [])
        cust = next((c for c in customers if c["customer_id"] == customer_id), None)
        txns = [t for t in data.get("txn", []) if t["customer_id"] == customer_id]

        narrative = generate_str_narrative(case, cust, txns, jurisdiction="CA")
        assert "Suspicious Transaction Report" in narrative
        assert "FINTRAC" in narrative

    def test_narrative_contains_case_data(self, tmp_path):
        spec, data, result = _run_ca(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        import json

        case_files = sorted((run_dir / "cases").glob("structuring*"))
        if not case_files:
            return
        case = json.loads(case_files[0].read_bytes())
        cust_id = case.get("alert", {}).get("customer_id", "")
        cust = next((c for c in data["customer"] if c["customer_id"] == cust_id), None)

        narrative = generate_str_narrative(case, cust, [], jurisdiction="CA")
        assert cust_id in narrative
        if cust:
            assert cust["full_name"] in narrative

    def test_us_jurisdiction_produces_sar(self):
        narrative = generate_str_narrative(
            case={
                "case_id": "test",
                "rule_name": "test_rule",
                "severity": "high",
                "alert": {"sum_amount": 10000},
                "regulation_refs": [],
                "queue": "l1",
            },
            customer={
                "full_name": "Test User",
                "customer_id": "T001",
                "country": "US",
                "risk_rating": "high",
            },
            transactions=[],
            jurisdiction="US",
        )
        assert "Suspicious Activity Report" in narrative
        assert "FinCEN" in narrative


# ---------------------------------------------------------------------------
# Board PDF
# ---------------------------------------------------------------------------


class TestBoardPDF:
    def test_generates_valid_pdf(self):
        from aml_framework.generators.board_pdf import generate_board_pdf

        spec = load_spec(EXAMPLE_CA)
        metrics = [
            {
                "id": "m1",
                "name": "Alert Volume",
                "value": 42,
                "rag": "green",
                "category": "operational",
            },
            {
                "id": "m2",
                "name": "SLA Compliance",
                "value": 0.95,
                "rag": "amber",
                "category": "operational",
            },
        ]
        cases = [
            {"case_id": "c1", "severity": "high", "status": "open"},
            {"case_id": "c2", "severity": "low", "status": "closed_no_action"},
        ]
        pdf_bytes = generate_board_pdf(spec=spec, metrics=metrics, cases=cases)
        assert len(pdf_bytes) > 100
        assert pdf_bytes[:5] == b"%PDF-"

    def test_with_maturity_scores(self):
        from aml_framework.dashboard.maturity import compute_maturity_scores
        from aml_framework.generators.board_pdf import generate_board_pdf

        spec = load_spec(EXAMPLE_CA)
        maturity = compute_maturity_scores(spec)
        pdf_bytes = generate_board_pdf(spec=spec, metrics=[], cases=[], maturity_scores=maturity)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_empty_metrics_and_cases(self):
        from aml_framework.generators.board_pdf import generate_board_pdf

        spec = load_spec(EXAMPLE_US)
        pdf_bytes = generate_board_pdf(spec=spec, metrics=[], cases=[])
        assert len(pdf_bytes) > 100
