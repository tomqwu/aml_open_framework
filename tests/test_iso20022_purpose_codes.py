"""ISO 20022 purpose-code typology library tests.

Round-5 PR #3 — composes with PR #56 ingestion (purpose_code column)
and the EU bank spec's new INVS-velocity demo rule.

Three layers:
  - The library YAML file is parseable spec rules (snippet validity).
  - The reference CSV has every code we cite from snippets.
  - The demo rule on eu_bank.yaml fires on a hand-built txn dict that
    exercises the INVS purpose code through the engine end-to-end.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from aml_framework.spec import load_spec
from aml_framework.spec.library import LIBRARY_ROOT
from aml_framework.spec.models import Rule

LIBRARY_FILE = LIBRARY_ROOT / "iso20022_purpose_codes.yaml"
HIGH_RISK_CSV = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "lists"
    / "iso20022_high_risk_purpose_codes.csv"
)
SPEC_EU = Path(__file__).resolve().parents[1] / "examples" / "eu_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Library YAML — every snippet must be a valid Rule
# ---------------------------------------------------------------------------


class TestLibraryYAML:
    def test_library_file_exists(self):
        assert LIBRARY_FILE.exists(), f"library file missing at {LIBRARY_FILE}"

    def test_library_loads_as_yaml_list(self):
        data = yaml.safe_load(LIBRARY_FILE.read_text())
        assert isinstance(data, list)
        assert len(data) >= 4  # v1 ships at least 4 snippets

    def test_every_snippet_is_a_valid_rule(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        for snippet in snippets:
            # Pydantic-validate each snippet as a Rule.
            rule = Rule.model_validate(snippet)
            assert rule.id
            assert rule.regulation_refs  # every snippet must cite something
            assert rule.tags  # tag-driven coverage downstream

    def test_every_snippet_targets_iso20022_tag(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        for snippet in snippets:
            assert "iso20022" in snippet["tags"], (
                f"snippet {snippet['id']!r} must carry the iso20022 tag"
            )

    def test_known_snippets_present(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        ids = {s["id"] for s in snippets}
        assert "invs_velocity_investment_scam" in ids
        assert "char_gift_burst_shell_charity" in ids
        assert "deri_from_retail_mandate_mismatch" in ids
        assert "trad_to_high_risk_jurisdiction_tbml" in ids


# ---------------------------------------------------------------------------
# Reference CSV — purpose codes referenced by snippets must be classified
# ---------------------------------------------------------------------------


class TestHighRiskCSV:
    def test_csv_exists(self):
        assert HIGH_RISK_CSV.exists()

    def test_csv_has_required_columns(self):
        with HIGH_RISK_CSV.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col in ("code", "category", "risk_band", "typology", "notes"):
                    assert col in row, f"missing column {col!r} on row {row}"
                break  # one row is enough to verify the schema

    def test_high_risk_codes_classified(self):
        codes_in_csv = _all_codes_in_csv()
        # Snippets cite these codes — they MUST be classified in the CSV.
        for cited in ("INVS", "CHAR", "GIFT", "DERI", "TRAD"):
            assert cited in codes_in_csv, (
                f"snippet cites {cited!r} but it isn't in the high-risk CSV"
            )

    def test_risk_band_values_are_valid(self):
        valid_bands = {"low", "medium", "high"}
        with HIGH_RISK_CSV.open() as f:
            for row in csv.DictReader(f):
                assert row["risk_band"] in valid_bands, (
                    f"row {row['code']!r} has invalid risk_band {row['risk_band']!r}"
                )

    def test_no_duplicate_codes(self):
        codes = list(_all_codes_in_csv())
        assert len(codes) == len(set(codes))


def _all_codes_in_csv() -> set[str]:
    with HIGH_RISK_CSV.open() as f:
        return {row["code"] for row in csv.DictReader(f)}


# ---------------------------------------------------------------------------
# EU bank spec — INVS-velocity rule wired in
# ---------------------------------------------------------------------------


class TestEUBankWiring:
    def test_eu_spec_now_has_invs_rule(self):
        spec = load_spec(SPEC_EU)
        rule_ids = {r.id for r in spec.rules}
        assert "invs_velocity_investment_scam" in rule_ids

    def test_purpose_code_column_declared_on_txn_contract(self):
        spec = load_spec(SPEC_EU)
        txn = next(c for c in spec.data_contracts if c.id == "txn")
        col_names = {c.name for c in txn.columns}
        assert "purpose_code" in col_names

    def test_invs_rule_has_tuning_grid(self):
        spec = load_spec(SPEC_EU)
        rule = next(r for r in spec.rules if r.id == "invs_velocity_investment_scam")
        assert rule.tuning_grid is not None
        assert "logic.having.count" in rule.tuning_grid


# ---------------------------------------------------------------------------
# End-to-end: rule fires on a hand-built txn batch with INVS spam
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_invs_rule_fires_on_planted_positives(self, tmp_path):
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_EU)
        # 3 INVS-purpose outbound transfers from one customer over 14 days
        # — exactly the snippet's threshold (count ≥ 3, sum ≥ 5000).
        txns = [
            {
                "txn_id": f"INVS-{i}",
                "customer_id": "C0099",
                "amount": Decimal("2500.00"),
                "currency": "EUR",
                "channel": "wire",
                "direction": "out",
                "booked_at": datetime(2026, 4, 20 + i),
                "purpose_code": "INVS",
                "counterparty_country": "CH",
            }
            for i in range(3)
        ]
        # Plus one non-INVS transfer that should NOT fire the rule.
        txns.append(
            {
                "txn_id": "GDDS-1",
                "customer_id": "C0099",
                "amount": Decimal("3000.00"),
                "currency": "EUR",
                "channel": "wire",
                "direction": "out",
                "booked_at": datetime(2026, 4, 25),
                "purpose_code": "GDDS",
                "counterparty_country": "FR",
            }
        )
        # Customer must exist for the EU spec's other rules not to crash.
        customers = [
            {
                "customer_id": "C0099",
                "full_name": "Test Subject",
                "country": "DE",
                "risk_rating": "medium",
                "onboarded_at": datetime(2024, 1, 1),
                "business_activity": "retail",
                "edd_last_review": None,
                "pep_status": None,
            }
        ]
        result = run_spec(
            spec=spec,
            spec_path=SPEC_EU,
            data={"txn": txns, "customer": customers},
            as_of=datetime(2026, 4, 27, 12, 0, 0),
            artifacts_root=tmp_path,
        )
        invs_alerts = result.alerts.get("invs_velocity_investment_scam", [])
        assert len(invs_alerts) == 1
        a = invs_alerts[0]
        assert a["customer_id"] == "C0099"
        # Sum should be 3 × 2500 = 7500 (excludes GDDS row).
        assert Decimal(str(a.get("sum_amount"))) == Decimal("7500.00")
        assert a.get("count") == 3

    def test_below_threshold_no_alert(self, tmp_path):
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_EU)
        # Only 2 INVS transfers — below the count gte=3 threshold.
        txns = [
            {
                "txn_id": f"INVS-{i}",
                "customer_id": "C0099",
                "amount": Decimal("3000.00"),
                "currency": "EUR",
                "channel": "wire",
                "direction": "out",
                "booked_at": datetime(2026, 4, 20 + i),
                "purpose_code": "INVS",
                "counterparty_country": "CH",
            }
            for i in range(2)
        ]
        customers = [
            {
                "customer_id": "C0099",
                "full_name": "Test Subject",
                "country": "DE",
                "risk_rating": "medium",
                "onboarded_at": datetime(2024, 1, 1),
                "business_activity": "retail",
                "edd_last_review": None,
                "pep_status": None,
            }
        ]
        result = run_spec(
            spec=spec,
            spec_path=SPEC_EU,
            data={"txn": txns, "customer": customers},
            as_of=datetime(2026, 4, 27, 12, 0, 0),
            artifacts_root=tmp_path,
        )
        assert result.alerts.get("invs_velocity_investment_scam", []) == []

    def test_synthetic_data_fires_invs_planted_positive(self, tmp_path):
        """Synthetic data now carries ISO 20022 enrichment (purpose_code,
        UETR, BICs) and includes a planted INVS-velocity positive on
        C0010 — three outbound INVS wires to CH within 14 days, sum
        > 5000 EUR. This makes the rule visible in the default `aml
        run` demo so operators see Round-5 features in action.
        Composes with the synthetic-data enrichment landed in the
        same PR as this test update."""
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_EU)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_EU,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        invs_alerts = result.alerts.get("invs_velocity_investment_scam", [])
        # Exactly the planted positive — C0010 with 3 INVS wires summing
        # to 8300 EUR. Operators tuning the rule should adjust their
        # data, not this test.
        assert len(invs_alerts) == 1, (
            f"expected exactly 1 INVS-velocity alert (the planted positive "
            f"on C0010); got {len(invs_alerts)}"
        )
        assert invs_alerts[0]["customer_id"] == "C0010"
        assert invs_alerts[0]["count"] == 3


@pytest.fixture(autouse=True)
def _cleanup():
    """Module-scoped helper — currently no global state to clean."""
    yield
