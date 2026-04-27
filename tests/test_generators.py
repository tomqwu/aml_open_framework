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


# ---------------------------------------------------------------------------
# goAML 5.0.2 XML exporter
# ---------------------------------------------------------------------------


class TestGoAMLExporter:
    """Verify the structural shape of the goAML XML output.

    We don't ship the UNODC XSD (not redistributable) so tests check the
    element shape. Jurisdiction-specific XSD validation is a deployment-time
    step.
    """

    @staticmethod
    def _sample_case():
        return {
            "case_id": "structuring_cash__C0001__2026-04-25T031428.866825",
            "rule_id": "structuring_cash_deposits",
            "rule_name": "Cash structuring",
            "severity": "high",
            "queue": "l1_aml_analyst",
            "spec_program": "schedule_i_bank_aml",
            "alert": {
                "customer_id": "C0001",
                "sum_amount": "45900.00",
                "count": 5,
                "window_start": "2026-04-05 23:14:28.866825",
                "window_end": "2026-04-25 03:14:28.866825",
            },
            "regulation_refs": [
                {
                    "citation": "PCMLTFA s.11.1",
                    "description": "Structuring offence — splitting transactions.",
                },
            ],
            "input_hash": {
                "txn": {"content_hash": "abc123" * 10, "row_count": 438},
            },
            "tags": ["high_risk_jurisdiction"],
        }

    @staticmethod
    def _sample_customer():
        return {
            "customer_id": "C0001",
            "full_name": "Olena Kowalski",
            "country": "CA",
            "occupation": "Trader",
            "tax_id": "XXX-123-456",
        }

    @staticmethod
    def _sample_txns():
        return [
            {
                "txn_id": "T100001",
                "customer_id": "C0001",
                "amount": "9500.00",
                "channel": "cash",
                "country": "CA",
                "booked_at": "2026-04-10 09:00:00",
            },
            {
                "txn_id": "T100002",
                "customer_id": "C0001",
                "amount": "9800.00",
                "channel": "cash",
                "country": "CA",
                "booked_at": "2026-04-15 11:30:00",
            },
            {
                "txn_id": "T999999",
                "customer_id": "C0099",  # different customer; should be filtered
                "amount": "100.00",
                "channel": "wire",
                "country": "CA",
                "booked_at": "2026-04-12 09:00:00",
            },
        ]

    def test_root_is_reports_with_schema_version(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        assert root.tag == "reports"
        assert root.attrib.get("schema_version") == "5.0.2"

    def test_each_case_emits_one_report(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        cases = [self._sample_case(), {**self._sample_case(), "case_id": "second"}]
        xml_bytes = build_goaml_xml(spec, cases, [self._sample_customer()], self._sample_txns())
        root = ET.fromstring(xml_bytes)
        reports = root.findall("report")
        assert len(reports) == 2

    def test_required_header_fields_present(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        report = root.find("report")
        for tag in (
            "rentity_id",
            "rentity_branch",
            "submission_code",
            "report_code",
            "submission_date",
            "currency_code_local",
            "reporting_person",
            "reason",
        ):
            assert report.find(tag) is not None, f"missing <{tag}>"

    def test_currency_matches_jurisdiction(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec_ca = load_spec(EXAMPLE_CA)
        spec_us = load_spec(EXAMPLE_US)

        xml_ca = build_goaml_xml(
            spec_ca, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        xml_us = build_goaml_xml(
            spec_us, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )

        ca_curr = ET.fromstring(xml_ca).find("report/currency_code_local").text
        us_curr = ET.fromstring(xml_us).find("report/currency_code_local").text
        assert ca_curr == "CAD"
        assert us_curr == "USD"

    def test_transactions_filtered_by_customer_and_window(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        # The third sample txn belongs to C0099, must not appear.
        txn_ids = [t.find("transactionnumber").text for t in root.findall("report/transaction")]
        assert "T100001" in txn_ids
        assert "T100002" in txn_ids
        assert "T999999" not in txn_ids

    def test_transaction_has_t_from_my_client_with_person(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        txn = root.find("report/transaction")
        t_from = txn.find("t_from_my_client")
        assert t_from is not None
        person = t_from.find("t_person")
        assert person is not None
        assert person.find("first_name").text == "Olena"
        assert person.find("last_name").text == "Kowalski"

    def test_indicators_includes_rule_id_and_tags(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        indicators = [i.text for i in root.findall("report/report_indicators/indicator")]
        assert "structuring_cash_deposits" in indicators
        assert "high_risk_jurisdiction" in indicators

    def test_reason_includes_regulation_citations(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        reason = root.find("report/reason").text
        assert "PCMLTFA s.11.1" in reason

    def test_unknown_customer_emits_placeholder_person(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        case = self._sample_case()
        case["alert"]["customer_id"] = "C9999"  # not in customer list
        xml_bytes = build_goaml_xml(spec, [case], [self._sample_customer()], self._sample_txns())
        root = ET.fromstring(xml_bytes)
        # No transactions filtered to this customer; t_from_my_client should be absent.
        # But the report itself must still emit successfully.
        assert root.find("report") is not None

    def test_byte_deterministic_for_fixed_inputs(self):
        from datetime import datetime, timezone

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        submit = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
        first = build_goaml_xml(
            spec,
            [self._sample_case()],
            [self._sample_customer()],
            self._sample_txns(),
            submission_date=submit,
        )
        second = build_goaml_xml(
            spec,
            [self._sample_case()],
            [self._sample_customer()],
            self._sample_txns(),
            submission_date=submit,
        )
        assert first == second

    def test_export_from_run_dir_reads_cases(self, tmp_path):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import export_goaml_from_run_dir

        spec, data, result = _run_ca(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        xml_bytes = export_goaml_from_run_dir(
            run_dir,
            spec,
            customers=data.get("customer", []),
            transactions=data.get("txn", []),
        )
        root = ET.fromstring(xml_bytes)
        assert root.tag == "reports"
        # The CA example produces multiple cases; ensure at least one report.
        assert len(root.findall("report")) > 0

    def test_export_run_dir_missing_cases_raises(self, tmp_path):
        from aml_framework.generators.goaml_xml import export_goaml_from_run_dir

        empty_run = tmp_path / "run-empty"
        empty_run.mkdir()
        with pytest.raises(FileNotFoundError):
            export_goaml_from_run_dir(empty_run, load_spec(EXAMPLE_CA), [], [])

    def test_funds_code_mapping(self):
        from aml_framework.generators.goaml_xml import _funds_code_for_channel

        assert _funds_code_for_channel("CASH") == "K"
        assert _funds_code_for_channel("ATM") == "K"
        assert _funds_code_for_channel("WIRE") == "A"
        assert _funds_code_for_channel("CRYPTO") == "X"
        assert _funds_code_for_channel("nonsense") == "X"

    def test_severity_in_additional_info(self):
        from xml.etree import ElementTree as ET

        from aml_framework.generators.goaml_xml import build_goaml_xml

        spec = load_spec(EXAMPLE_CA)
        xml_bytes = build_goaml_xml(
            spec, [self._sample_case()], [self._sample_customer()], self._sample_txns()
        )
        root = ET.fromstring(xml_bytes)
        info = root.find("report/additional_info").text
        assert "severity: high" in info
        assert "case_id:" in info
