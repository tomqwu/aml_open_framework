"""Focused edge-case tests for the 99% coverage gate.

These assert documented fallback behavior on helpers that are otherwise
hard to reach through end-to-end specs.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from aml_framework.cases.aggregator import _STRATEGIES, aggregate_investigations, bucket_window_for
from aml_framework.cases.filing import get_filing, list_filings, record_filing
from aml_framework.cases.sla import _opened_at, compute_sla_status
from aml_framework.data.iso20022.parser import (
    _decimal,
    _extract_agent_bic,
    _extract_pain001_amount,
    _extract_returned_amount,
    _extract_structured_remittance,
    _parse_iso_date,
)
from aml_framework.data.psd3.parser import parse_vop_response
from aml_framework.integrations.digest import (
    DigestEntry,
    DigestPayload,
    _parse_iso,
    build_digest,
)
from aml_framework.metrics.outcomes import OutcomesReport, RuleOutcome, compute_outcomes
from aml_framework.models.travel_rule import _crosses_threshold, _resolve_thresholds
from aml_framework.spec.models import Queue
from aml_framework.typology_library import _render_rule_yaml, import_typology, list_typologies


def test_iso20022_parser_edge_fallbacks() -> None:
    assert _decimal(None) == Decimal("0")
    assert _decimal("not-a-decimal") == Decimal("0")
    assert _parse_iso_date("") is None
    assert _parse_iso_date("not-a-date") is None

    no_agent = ET.fromstring("<Tx />")
    assert _extract_agent_bic(no_agent, "DbtrAgt") == ""

    no_fin = ET.fromstring("<Tx><DbtrAgt /></Tx>")
    assert _extract_agent_bic(no_fin, "DbtrAgt") == ""

    legacy_bic = ET.fromstring(
        "<Tx><DbtrAgt><FinInstnId><BIC>DEUTDEFFXXX</BIC></FinInstnId></DbtrAgt></Tx>"
    )
    assert _extract_agent_bic(legacy_bic, "DbtrAgt") == "DEUTDEFFXXX"

    assert _extract_structured_remittance(ET.fromstring("<Tx />")) is None
    assert _extract_structured_remittance(ET.fromstring("<Tx><RmtInf /></Tx>")) is None

    assert _extract_pain001_amount(ET.fromstring("<Tx />")) == (Decimal("0"), "")
    assert _extract_pain001_amount(ET.fromstring("<Tx><Amt /></Tx>")) == (Decimal("0"), "")
    assert _extract_returned_amount(ET.fromstring("<Tx />")) == (Decimal("0"), "")


def test_aggregation_skips_unactionable_cases_and_tolerates_bad_values() -> None:
    cases = [
        {
            "case_id": "c1",
            "customer_id": "C1",
            "rule_id": "r1",
            "severity": "high",
            "queue": "q1",
            "evidence_requested": ["id_doc"],
            "alert": {
                "customer_id": "C1",
                "window_start": "not-a-date",
                "window_end": "not-a-date",
                "sum_amount": "not-a-decimal",
                "tags": ["wire"],
            },
        },
        {
            "case_id": "no-customer",
            "rule_id": "r2",
            "severity": "low",
            "alert": {"window_end": "also-bad"},
        },
    ]

    investigations = aggregate_investigations(cases, strategy="per_customer_window")
    assert len(investigations) == 1
    assert investigations[0]["customer_id"] == "C1"
    assert investigations[0]["total_amount"] == Decimal("0")
    assert investigations[0]["window_start"] is None
    assert investigations[0]["window_end"] is None

    assert aggregate_investigations([cases[1]], strategy="per_customer_per_run") == []
    assert aggregate_investigations([cases[1]], strategy="per_case") == []
    with pytest.raises(ValueError, match="unknown aggregation strategy"):
        aggregate_investigations(cases, strategy="bad")

    _STRATEGIES["empty_test"] = lambda _cases: {("C1", 0): []}
    try:
        assert aggregate_investigations(cases, strategy="empty_test") == []
    finally:
        del _STRATEGIES["empty_test"]

    start, end = bucket_window_for(datetime(2026, 1, 15))
    assert start < end


def test_sla_and_psd3_parser_malformed_fallbacks(monkeypatch) -> None:
    assert _opened_at(
        {
            "opened_at": "not-a-date",
            "alert": {
                "window_end": "also-bad",
                "booked_at": "2026-01-01T00:00:00Z",
            },
        }
    ) == datetime(2026, 1, 1)

    monkeypatch.setattr("aml_framework.cases.sla.parse_window", lambda _sla: timedelta(0))
    assert (
        compute_sla_status(
            {"case_id": "c1", "opened_at": "2026-01-01T00:00:00"},
            Queue(id="q1", sla="1h"),
            as_of=datetime(2026, 1, 1),
        )
        is None
    )

    parsed = parse_vop_response(
        {
            "requestId": "r1",
            "paymentId": "p1",
            "receivedAt": "not-a-date",
            "responseTimeMs": object(),
        }
    )
    assert parsed is not None
    assert parsed.received_at is None
    assert parsed.response_time_ms == 0


def test_filing_readers_skip_blank_and_malformed_jsonl(tmp_path) -> None:
    first = record_filing(
        tmp_path,
        "case-1",
        filed_at=datetime(2026, 1, 1),
        channel="goaml",
        reference_id="R1",
    )
    second = record_filing(
        tmp_path,
        "case-1",
        filed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        channel="goaml",
        reference_id="R2",
    )
    path = tmp_path / "cases" / "case-1__filing.jsonl"
    path.write_text(
        "\n"
        + json.dumps(first.to_dict(), default=str)
        + "\n"
        + "{bad-json\n"
        + json.dumps(second.to_dict(), default=str)
        + "\n"
        + json.dumps({"filed_at": "2026-01-03T00:00:00+00:00"})
        + "\n",
        encoding="utf-8",
    )

    assert get_filing(tmp_path, "missing") is None
    assert get_filing(tmp_path, "case-1").reference_id == "R2"
    assert [f.reference_id for f in list_filings(tmp_path)] == ["R1", "R2"]


def test_travel_rule_invalid_threshold_env_and_amounts(monkeypatch) -> None:
    monkeypatch.setenv(
        "AML_TRAVEL_RULE_THRESHOLDS",
        "not-a-pair,USD=bad,EUR=-1,GBP=0,CAD=750",
    )
    thresholds = _resolve_thresholds()
    assert thresholds["USD"] == Decimal("1000")
    assert thresholds["EUR"] == Decimal("1000")
    assert thresholds["GBP"] == Decimal("1000")
    assert thresholds["CAD"] == Decimal("750")

    assert _crosses_threshold({"amount": None, "currency": "CAD"}, thresholds) is False
    assert _crosses_threshold({"amount": object(), "currency": "CAD"}, thresholds) is False


def test_digest_serialization_and_empty_run_fallback(tmp_path) -> None:
    entry = DigestEntry(
        kind="alert",
        severity="critical",
        case_id="c1",
        customer_id="C1",
        rule_id="r1",
        occurred_at="2026-01-01T00:00:00",
        detail="detail",
    )
    payload = DigestPayload(
        program_name="AML",
        window_hours=24,
        window_end="2026-01-01T01:00:00",
        entries=[entry],
    )
    assert payload.critical_entries == [entry]
    assert payload.to_dict()["entries"][0]["detail"] == "detail"
    assert entry.to_dict()["kind"] == "alert"
    assert _parse_iso(None) is None
    assert _parse_iso("not-a-date") is None

    empty = build_digest(tmp_path, program_name="AML", as_of=datetime(2026, 1, 1))
    assert empty.total == 0
    assert empty.window_end.startswith("2026-01-01")


def test_outcomes_serialization_and_ruleless_cases_are_skipped() -> None:
    outcome = RuleOutcome(
        rule_id="r1",
        alerts=1,
        cases_opened=1,
        cases_escalated=0,
        str_filed=0,
        closed_no_action=0,
        pending=1,
        sla_breaches=0,
        sla_breach_rate_pct=0.0,
        precision=None,
        recall=None,
        true_positives=None,
        false_positives=None,
    )
    report = OutcomesReport(
        spec_program="AML",
        as_of="2026-01-01T00:00:00+00:00",
        total_alerts=1,
        total_cases=1,
        total_str_filed=0,
        total_closed_no_action=0,
        alert_to_case_pct=100.0,
        case_to_str_pct=0.0,
        alert_to_str_pct=0.0,
        sla_breach_rate_pct=0.0,
        rules=[outcome],
    )
    assert outcome.to_dict()["rule_id"] == "r1"
    assert report.to_dict()["totals"]["alerts"] == 1

    computed = compute_outcomes(
        [{"case_id": "c-missing-rule"}],
        [{"case_id": "", "event": "ignored"}],
        spec_program="AML",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert computed.total_alerts == 0
    assert computed.rules == []


def test_typology_import_edge_paths(tmp_path, monkeypatch) -> None:
    assert list_typologies(tmp_path / "missing") == []
    assert _render_rule_yaml({"id": "r1", "logic": {"type": "custom_sql", "sql": ""}}).startswith(
        "  - id: r1"
    )
    assert "\n\n" not in _render_rule_yaml({"id": "r1", "description": "", "tags": []})
    with monkeypatch.context() as m:
        m.setattr(
            "aml_framework.typology_library.yaml.dump",
            lambda *_args, **_kwargs: "id: r1\n\nname: Rule\n",
        )
        assert _render_rule_yaml({"id": "r1"}) == "  - id: r1\n\n    name: Rule\n"

    typology_dir = tmp_path / "typologies"
    typology_dir.mkdir()
    (typology_dir / "missing-rule-id.yaml").write_text(
        "metadata:\n  id: missing-rule-id\n  name: Missing Rule ID\n  source: test\n"
        "rule:\n  name: No ID\n",
        encoding="utf-8",
    )
    (typology_dir / "t1.yaml").write_text(
        "metadata:\n  id: t1\n  name: T1\n  source: test\n"
        "rule:\n  id: new_rule\n  name: New Rule\n  severity: low\n"
        "  logic:\n    type: custom_sql\n    sql: select 1 where false\n",
        encoding="utf-8",
    )
    spec = tmp_path / "aml.yaml"
    with pytest.raises(ValueError, match="missing a `rule.id`"):
        import_typology("missing-rule-id", spec, typology_dir=typology_dir)

    spec.write_text("program:\n  name: no rules\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no top-level `rules:` block"):
        import_typology("t1", spec, typology_dir=typology_dir)

    spec.write_text("rules:\n", encoding="utf-8")

    class _LoadedSpec:
        rules = []

    monkeypatch.setattr("aml_framework.spec.load_spec", lambda _path: _LoadedSpec())
    with pytest.raises(ValueError, match="Loader did not register"):
        import_typology("t1", spec, typology_dir=typology_dir)
