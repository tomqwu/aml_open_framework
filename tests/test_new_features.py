"""Tests for list_match, STR narrative, data quality, and sanctions screening."""

from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.generators.narrative import generate_str_narrative
from aml_framework.spec import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _run(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return (
        spec,
        data,
        run_spec(
            spec=spec,
            spec_path=EXAMPLE,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        ),
    )


# --- Sanctions / list_match tests ---


class TestSanctionsScreening:
    def test_list_match_rule_fires(self, tmp_path):
        _, _, result = _run(tmp_path)
        alerts = result.alerts.get("sanctions_screening", [])
        assert len(alerts) >= 1, "sanctions_screening must produce at least one match"

    def test_planted_sanctions_match(self, tmp_path):
        """Alexei Volkov (C0003) is in both customer data and sanctions list."""
        _, _, result = _run(tmp_path)
        alerts = result.alerts.get("sanctions_screening", [])
        matched_customers = {a["customer_id"] for a in alerts}
        assert "C0003" in matched_customers, "C0003 (Alexei Volkov) must match sanctions list"

    def test_match_has_score(self, tmp_path):
        _, _, result = _run(tmp_path)
        for alert in result.alerts.get("sanctions_screening", []):
            assert "match_score" in alert
            assert alert["match_score"] >= 0.8

    def test_sanctions_creates_cases(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        sanctions_cases = list((run_dir / "cases").glob("sanctions_screening__*"))
        assert len(sanctions_cases) >= 1


# --- STR narrative tests ---


class TestSTRNarrative:
    def test_narrative_generates(self, tmp_path):
        spec, data, result = _run(tmp_path)
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
        spec, data, result = _run(tmp_path)
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


# --- Data quality tests ---


class TestDataQuality:
    def test_quality_checks_in_spec(self):
        spec = load_spec(EXAMPLE)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        assert len(txn_contract.quality_checks) > 0, "txn contract must have quality checks"

    def test_not_null_check_passes_on_synthetic_data(self, tmp_path):
        """Synthetic data should have no nulls in required fields."""
        spec = load_spec(EXAMPLE)
        data = generate_dataset(as_of=datetime(2026, 4, 23, 12, 0, 0), seed=42)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        for qc in txn_contract.quality_checks:
            if "not_null" in qc:
                for field in qc["not_null"]:
                    for row in data["txn"]:
                        assert row.get(field) is not None, f"{field} has null in txn data"

    def test_unique_check_passes_on_synthetic_data(self, tmp_path):
        spec = load_spec(EXAMPLE)
        data = generate_dataset(as_of=datetime(2026, 4, 23, 12, 0, 0), seed=42)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        for qc in txn_contract.quality_checks:
            if "unique" in qc:
                for field in qc["unique"]:
                    values = [row[field] for row in data["txn"]]
                    assert len(values) == len(set(values)), f"{field} has duplicates"


# --- Case resolution tests ---


class TestCaseResolution:
    def test_cases_have_resolution(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        import json

        resolved = 0
        for f in (run_dir / "cases").glob("*.json"):
            case = json.loads(f.read_bytes())
            if case.get("resolved_at"):
                resolved += 1
        assert resolved > 0, "at least some cases should be resolved"

    def test_decision_log_has_resolution_events(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        decisions = (run_dir / "decisions.jsonl").read_text().splitlines()
        import json

        resolution_events = [
            json.loads(d)
            for d in decisions
            if json.loads(d).get("event") in ("escalated", "escalated_to_str", "closed")
        ]
        assert len(resolution_events) > 0

    def test_sla_data_in_decisions(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        import json

        for line in (run_dir / "decisions.jsonl").read_text().splitlines():
            d = json.loads(line)
            if d.get("event") in ("escalated", "escalated_to_str", "closed"):
                assert "resolution_hours" in d
                assert "within_sla" in d
                break
