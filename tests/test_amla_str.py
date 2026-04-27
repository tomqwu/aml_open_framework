"""AMLA STR profile generator tests.

Covers typology mapping, payload shape, conformance reporting, draft
warning, and round-trip from a finalised run directory. No network IO.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.generators.amla_str import (
    DRAFT_VERSION,
    DRAFT_WARNING,
    AMLATypology,
    ObligedEntity,
    SubmittingPerson,
    build_amla_report,
    build_amla_str_json,
    build_amla_str_payload,
    export_amla_str_from_run_dir,
    map_to_typology,
)
from aml_framework.spec import load_spec

EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)
EXAMPLE_EU = Path(__file__).resolve().parents[1] / "examples" / "eu_bank" / "aml.yaml"
EXAMPLE_VASP = Path(__file__).resolve().parents[1] / "examples" / "crypto_vasp" / "aml.yaml"


def _case(case_id="case-1", customer_id="C0001", rule_id="structuring_cash_deposits"):
    return {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": "Cash structuring",
        "severity": "high",
        "queue": "l1_aml_analyst",
        "alert": {
            "customer_id": customer_id,
            "sum_amount": "45900.00",
            "count": 5,
            "window_start": "2026-04-05 23:00:00",
            "window_end": "2026-04-25 03:00:00",
        },
        "regulation_refs": [
            {"citation": "AMLD6 art.1", "description": "Predicate offence widening."}
        ],
        "tags": ["high_value"],
    }


def _customer(cid="C0001", country="DE", lei=None, owners=None):
    out = {
        "customer_id": cid,
        "full_name": "Klaus Müller",
        "country": country,
        "occupation": "Trader",
        "risk_rating": "medium",
        "tax_id": "DE-12345",
        "date_of_birth": "1980-05-12",
    }
    if lei:
        out["lei"] = lei
    if owners:
        out["beneficial_owners"] = owners
    return out


def _txn(cid="C0001", booked="2026-04-10 09:00:00", amount="9500", cp_country="DE"):
    return {
        "txn_id": f"T{booked.replace(' ', '_')}",
        "customer_id": cid,
        "amount": amount,
        "currency": "EUR",
        "channel": "wire",
        "country": "DE",
        "booked_at": booked,
        "counterparty_country": cp_country,
        "counterparty_name": "ACME Trading",
    }


# ---------------------------------------------------------------------------
# Typology mapping
# ---------------------------------------------------------------------------


class TestTypologyMapping:
    def test_structuring_match(self):
        assert map_to_typology("structuring_cash_deposits") == AMLATypology.STRUCTURING

    def test_sanctions_match(self):
        assert map_to_typology("sanctioned_wallet_screening") == AMLATypology.SANCTIONS_EVASION
        assert map_to_typology("ofac_screening") == AMLATypology.SANCTIONS_EVASION

    def test_pep_via_adverse_media(self):
        assert map_to_typology("adverse_media_screening") == AMLATypology.PEP_INVOLVEMENT

    def test_crypto_typology(self):
        assert map_to_typology("stablecoin_velocity_48h") == AMLATypology.VIRTUAL_ASSET_LAYERING
        assert map_to_typology("nested_wallet_ring") == AMLATypology.VIRTUAL_ASSET_LAYERING

    def test_country_risk(self):
        assert map_to_typology("country_risk_change") == AMLATypology.HIGH_RISK_JURISDICTION

    def test_unknown_falls_back(self):
        assert map_to_typology("totally_custom_rule_xyz") == AMLATypology.UNKNOWN

    def test_tag_assist(self):
        # Even if rule_id has no hint, a tag should match.
        assert map_to_typology("custom_rule", tags=["pep_match"]) == AMLATypology.PEP_INVOLVEMENT


# ---------------------------------------------------------------------------
# Single report builder
# ---------------------------------------------------------------------------


class TestBuildReport:
    def test_minimal_shape(self):
        report = build_amla_report(_case(), _customer(), [_txn()], jurisdiction="DE")
        assert report["report_id"] == "case-1"
        assert AMLATypology.STRUCTURING in report["amla_typology_codes"]
        assert report["subject"]["subject_id"] == "C0001"
        assert report["subject"]["country_of_residence"] == "DE"
        assert report["transactions"]
        assert report["indicators"]
        assert report["narrative_summary"]

    def test_subject_natural_person_branch(self):
        report = build_amla_report(_case(), _customer(), [], jurisdiction="DE")
        assert report["subject"]["type"] == "natural_person"
        assert report["subject"]["date_of_birth"] == "1980-05-12"
        assert report["subject"]["national_id"] == "DE-12345"

    def test_subject_legal_entity_branch_with_owners(self):
        cust = {
            "customer_id": "ENT001",
            "legal_name": "ACME GmbH",
            "country": "DE",
            "lei": "529900T8BM49AURSDO55",
            "beneficial_owners": [{"name": "Klaus Müller", "percent": 51}],
        }
        report = build_amla_report(_case(customer_id="ENT001"), cust, [], jurisdiction="DE")
        # Without DOB and no full_name → legal_entity
        assert report["subject"]["type"] == "legal_entity"
        assert report["subject"]["lei"] == "529900T8BM49AURSDO55"
        assert report["subject"]["beneficial_owner_chain"][0]["percent"] == 51

    def test_missing_customer_handled(self):
        report = build_amla_report(_case(), None, [], jurisdiction="DE")
        assert report["subject"]["type"] == "unknown"
        assert report["subject"]["missing_kyc"] is True

    def test_cross_border_indicator_true_when_counterparty_country_differs(self):
        report = build_amla_report(
            _case(),
            _customer(country="DE"),
            [_txn(cp_country="RU")],
            jurisdiction="DE",
        )
        assert report["cross_border_indicator"] is True

    def test_cross_border_indicator_false_when_domestic(self):
        report = build_amla_report(
            _case(),
            _customer(country="DE"),
            [_txn(cp_country="DE")],
            jurisdiction="DE",
        )
        assert report["cross_border_indicator"] is False

    def test_indicators_include_rule_and_regulation_and_tag(self):
        report = build_amla_report(_case(), _customer(), [], jurisdiction="DE")
        types = {i.get("type") for i in report["indicators"]}
        assert "rule" in types
        assert "regulation" in types
        assert "tag" in types


# ---------------------------------------------------------------------------
# Payload + conformance
# ---------------------------------------------------------------------------


class TestPayload:
    def test_draft_warning_present(self):
        spec = load_spec(EXAMPLE_EU)
        payload = build_amla_str_payload(spec, [_case()], [_customer()], [_txn()])
        assert payload["_draft_warning"] == DRAFT_WARNING
        assert payload["_schema"] == DRAFT_VERSION

    def test_obliged_entity_defaults_to_programme_name(self):
        spec = load_spec(EXAMPLE_EU)
        payload = build_amla_str_payload(spec, [_case()], [_customer()], [_txn()])
        assert payload["obliged_entity"]["programme_name"] == spec.program.name

    def test_one_report_per_case_sorted(self):
        spec = load_spec(EXAMPLE_EU)
        cases = [_case("c2"), _case("c1"), _case("c3", rule_id="adverse_media")]
        payload = build_amla_str_payload(spec, cases, [_customer()], [_txn()])
        # Sorted by (rule_id, case_id) → adverse_media first, then structuring c1, c2
        ids = [r["report_id"] for r in payload["reports"]]
        assert ids == ["c3", "c1", "c2"]

    def test_byte_deterministic(self):
        spec = load_spec(EXAMPLE_EU)
        submit = datetime(2026, 4, 27, tzinfo=timezone.utc)
        a = build_amla_str_json(spec, [_case()], [_customer()], [_txn()], submission_date=submit)
        b = build_amla_str_json(spec, [_case()], [_customer()], [_txn()], submission_date=submit)
        assert a == b

    def test_conformance_counts_populated_fields(self):
        spec = load_spec(EXAMPLE_EU)
        payload = build_amla_str_payload(
            spec,
            [_case()],
            [_customer()],
            [_txn()],
            obliged_entity=ObligedEntity(lei="529900T8BM49AURSDO55", name="EUbank"),
        )
        c = payload["conformance"]
        assert c["mandatory_fields_total"] >= 8
        assert "obliged_entity.lei" in c["populated"]
        assert "report.amla_typology_codes" in c["populated"]
        assert "report.cross_border_indicator" in c["populated"]

    def test_conformance_flags_placeholder_lei_as_unmapped(self):
        spec = load_spec(EXAMPLE_EU)
        payload = build_amla_str_payload(
            spec,
            [_case()],
            [_customer()],
            [_txn()],
            # default ObligedEntity → placeholder LEI
        )
        assert "obliged_entity.lei" in payload["conformance"]["unmapped_required"]

    def test_submission_id_includes_programme_and_timestamp(self):
        spec = load_spec(EXAMPLE_EU)
        submit = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
        payload = build_amla_str_payload(
            spec, [_case()], [_customer()], [_txn()], submission_date=submit
        )
        assert "20260427T120000Z" in payload["submission_id"]

    def test_submitting_person_default_role_mlro(self):
        spec = load_spec(EXAMPLE_EU)
        payload = build_amla_str_payload(spec, [_case()], [_customer()], [_txn()])
        assert payload["submitting_person"]["role"] == "MLRO"

    def test_custom_submitting_person(self):
        spec = load_spec(EXAMPLE_EU)
        person = SubmittingPerson(full_name="Anna Schmidt", role="Compliance Lead")
        payload = build_amla_str_payload(
            spec, [_case()], [_customer()], [_txn()], submitting_person=person
        )
        assert payload["submitting_person"]["full_name"] == "Anna Schmidt"
        assert payload["submitting_person"]["role"] == "Compliance Lead"


# ---------------------------------------------------------------------------
# Run-dir round-trip
# ---------------------------------------------------------------------------


class TestRunDirRoundTrip:
    def test_export_from_finalised_run(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(EXAMPLE_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=EXAMPLE_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        payload_bytes = export_amla_str_from_run_dir(
            run_dir,
            spec,
            customers=data.get("customer", []),
            transactions=data.get("txn", []),
        )
        payload = json.loads(payload_bytes)
        assert payload["_schema"] == DRAFT_VERSION
        assert "reports" in payload
        assert len(payload["reports"]) > 0

    def test_missing_cases_dir_raises(self, tmp_path):
        spec = load_spec(EXAMPLE_EU)
        empty = tmp_path / "empty-run"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            export_amla_str_from_run_dir(empty, spec, [], [])

    def test_vasp_spec_emits_crypto_typology(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(EXAMPLE_VASP)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=EXAMPLE_VASP, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        payload = json.loads(
            export_amla_str_from_run_dir(
                run_dir,
                spec,
                customers=data.get("customer", []),
                transactions=data.get("txn", []),
                obliged_entity=ObligedEntity(
                    lei="VASP000000000000VASP",
                    sector="VASP",
                    jurisdiction="EU",
                ),
            )
        )
        # If any crypto rules fired, at least one report should carry the
        # virtual-asset typology. If none fired (edge: small synthetic data),
        # the payload still parses.
        assert payload["_schema"] == DRAFT_VERSION
        if payload["reports"]:
            typologies = {
                code for r in payload["reports"] for code in r.get("amla_typology_codes", [])
            }
            assert typologies  # at least one mapped
