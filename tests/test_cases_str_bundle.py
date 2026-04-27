"""Case-to-STR auto-bundling tests — Round-6 PR #4.

Verifies the per-investigation ZIP is well-formed, deterministic
(byte-identical for identical inputs), contains the expected file set
(investigation summary + per-case JSON + narrative + goAML XML +
network diagrams + manifest), and that the manifest hash chain is
consistent.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from aml_framework.cases import (
    BUNDLE_VERSION,
    aggregate_investigations,
    bundle_hash,
    bundle_investigation_to_str,
)
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _case(
    *,
    case_id: str,
    rule_id: str = "structuring_cash",
    customer_id: str = "C0001",
    severity: str = "high",
    sum_amount: Decimal | None = Decimal("12000.00"),
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    subgraph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    alert: dict[str, Any] = {
        "customer_id": customer_id,
        "count": 3,
    }
    if sum_amount is not None:
        alert["sum_amount"] = sum_amount
    if window_start is not None:
        alert["window_start"] = window_start
    if window_end is not None:
        alert["window_end"] = window_end
    if subgraph is not None:
        alert["subgraph"] = subgraph
    return {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "severity": severity,
        "regulation_refs": [{"citation": "PCMLTFA s.7", "description": "STR filing obligation"}],
        "queue": "l1_aml_analyst",
        "alert": alert,
        "evidence_requested": ["customer_kyc_profile"],
        "spec_program": "schedule_i_bank_aml",
        "input_hash": {},
        "status": "open",
    }


def _customer(customer_id: str = "C0001") -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "full_name": "Acme Corp",
        "country": "CA",
        "risk_rating": "high",
        "onboarded_at": datetime(2024, 1, 1),
    }


def _txn(
    *,
    txn_id: str,
    customer_id: str = "C0001",
    amount: Decimal = Decimal("4000.00"),
    booked_at: datetime = datetime(2026, 4, 15),
) -> dict[str, Any]:
    return {
        "txn_id": txn_id,
        "customer_id": customer_id,
        "amount": amount,
        "currency": "CAD",
        "channel": "cash",
        "direction": "in",
        "booked_at": booked_at,
    }


# ---------------------------------------------------------------------------
# Bundle structure
# ---------------------------------------------------------------------------


class TestBundleStructure:
    def test_bundle_is_valid_zip(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        # Round-trips through zipfile cleanly.
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            assert zf.testzip() is None

    def test_required_files_present(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = set(zf.namelist())
        assert "investigation.json" in names
        assert "manifest.json" in names
        assert "narrative.txt" in names
        assert "goaml_report.xml" in names
        assert "cases/c1.json" in names

    def test_no_network_dir_when_no_subgraph(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        # No subgraph payload — narrative + xml only.
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = zf.namelist()
        assert not any(n.startswith("network/") for n in names)

    def test_network_diagram_included_for_subgraph_case(self):
        spec = load_spec(SPEC_CA)
        subgraph = {
            "seed": "C0001",
            "pattern": "common_counterparty",
            "max_hops": 2,
            "nodes": [
                {"id": "C0001", "hops": 0},
                {"id": "C0007", "hops": 1},
                {"id": "MERCH_X", "hops": 2},
            ],
            "edges": [
                {"source": "C0001", "target": "MERCH_X", "attribute": "counterparty"},
                {"source": "C0007", "target": "MERCH_X", "attribute": "counterparty"},
            ],
            "topology_hash": "deadbeef",
            "summary": "two customers share one merchant",
        }
        case = _case(case_id="c1", subgraph=subgraph, window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = zf.namelist()
            assert "network/c1.mmd" in names
            mermaid = zf.read("network/c1.mmd").decode("utf-8")
        assert mermaid.startswith("graph TD")

    def test_per_case_json_round_trips(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            payload = json.loads(zf.read("cases/c1.json"))
        assert payload["case_id"] == "c1"
        assert payload["rule_id"] == "structuring_cash"

    def test_investigation_json_round_trips(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            payload = json.loads(zf.read("investigation.json"))
        assert payload["customer_id"] == "C0001"
        assert "c1" in payload["case_ids"]


# ---------------------------------------------------------------------------
# Manifest contract
# ---------------------------------------------------------------------------


class TestManifest:
    def _manifest(self, bundle: bytes) -> dict[str, Any]:
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            return json.loads(zf.read("manifest.json"))

    def test_manifest_has_required_keys(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        m = self._manifest(bundle)
        for key in (
            "bundle_version",
            "investigation_id",
            "case_count",
            "case_ids",
            "spec_program",
            "jurisdiction",
            "files",
            "bundle_hash",
        ):
            assert key in m, f"missing manifest key {key!r}"

    def test_manifest_version_matches_constant(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        assert self._manifest(bundle)["bundle_version"] == BUNDLE_VERSION

    def test_manifest_files_hashes_match_archive_contents(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        import hashlib

        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            for path, claimed_hash in manifest["files"].items():
                actual = hashlib.sha256(zf.read(path)).hexdigest()
                assert actual == claimed_hash, (
                    f"hash mismatch on {path}: claimed {claimed_hash}, actual {actual}"
                )

    def test_manifest_self_hash_is_not_in_files_list(self):
        # The manifest hashes everything BUT itself (chicken-egg avoidance).
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        m = self._manifest(bundle)
        assert "manifest.json" not in m["files"]

    def test_manifest_records_constituent_case_count(self):
        spec = load_spec(SPEC_CA)
        cases = [
            _case(case_id="c1", window_end=datetime(2026, 4, 15)),
            _case(case_id="c2", rule_id="rapid_movement", window_end=datetime(2026, 4, 18)),
        ]
        invs = aggregate_investigations(cases)
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=cases,
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        m = self._manifest(bundle)
        assert m["case_count"] == 2
        assert sorted(m["case_ids"]) == ["c1", "c2"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_bundle_bytes(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        b1 = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        b2 = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        assert b1 == b2
        assert bundle_hash(b1) == bundle_hash(b2)

    def test_case_order_does_not_change_bundle(self):
        spec = load_spec(SPEC_CA)
        c1 = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        c2 = _case(case_id="c2", rule_id="rapid_movement", window_end=datetime(2026, 4, 18))
        invs = aggregate_investigations([c1, c2])
        b1 = bundle_investigation_to_str(
            invs[0],
            cases=[c1, c2],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        b2 = bundle_investigation_to_str(
            invs[0],
            cases=[c2, c1],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        assert b1 == b2

    def test_extraneous_cases_do_not_affect_bundle(self):
        # Cases not in the investigation's case_ids list are silently dropped.
        spec = load_spec(SPEC_CA)
        c1 = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        c_other = _case(case_id="OTHER", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([c1])
        b_just = bundle_investigation_to_str(
            invs[0],
            cases=[c1],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        b_with_extra = bundle_investigation_to_str(
            invs[0],
            cases=[c1, c_other],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        assert b_just == b_with_extra


# ---------------------------------------------------------------------------
# Narrative content
# ---------------------------------------------------------------------------


class TestNarrative:
    def test_narrative_mentions_each_constituent_case_id(self):
        spec = load_spec(SPEC_CA)
        cases = [
            _case(case_id="case-a", window_end=datetime(2026, 4, 15)),
            _case(case_id="case-b", rule_id="rapid_movement", window_end=datetime(2026, 4, 18)),
        ]
        invs = aggregate_investigations(cases)
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=cases,
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            narrative = zf.read("narrative.txt").decode("utf-8")
        assert "case-a" in narrative
        assert "case-b" in narrative

    def test_narrative_includes_jurisdiction(self):
        spec = load_spec(SPEC_CA)  # jurisdiction = CA
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            narrative = zf.read("narrative.txt").decode("utf-8")
        # Narrative template names FINTRAC for CA jurisdiction.
        assert "FINTRAC" in narrative or "STR" in narrative


# ---------------------------------------------------------------------------
# goAML XML content
# ---------------------------------------------------------------------------


class TestGoamlXml:
    def test_xml_is_well_formed(self):
        import xml.etree.ElementTree as ET

        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[_txn(txn_id="t1")],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            xml_bytes = zf.read("goaml_report.xml")
        # Doesn't raise.
        root = ET.fromstring(xml_bytes)
        assert root.tag == "reports"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_constituent_set_still_produces_valid_bundle(self):
        # Investigation references case_ids that don't appear in the
        # passed cases list — we get a bundle with just investigation.json
        # and manifest.json (and an empty narrative).
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[],
            spec=spec,  # filtered to empty
            customers=[],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = set(zf.namelist())
        assert "investigation.json" in names
        assert "manifest.json" in names
        # narrative.txt always emitted, even when empty.
        assert "narrative.txt" in names

    def test_case_with_unknown_customer_does_not_crash(self):
        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", customer_id="GHOST", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[],  # GHOST not in customer table
            transactions=[],
        )
        # Bundle still produced, narrative lists Unknown customer.
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            narrative = zf.read("narrative.txt").decode("utf-8")
        assert "Unknown" in narrative or len(narrative) > 0

    def test_malformed_subgraph_does_not_crash_bundle(self):
        spec = load_spec(SPEC_CA)
        # Subgraph missing required fields.
        case = _case(
            case_id="c1",
            subgraph={"bogus": "data"},
            window_end=datetime(2026, 4, 15),
        )
        invs = aggregate_investigations([case])
        # Should not raise.
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            names = zf.namelist()
        # Network diagram skipped, but bundle still valid.
        assert not any(n.startswith("network/") for n in names)
        assert "manifest.json" in names

    def test_decimal_amounts_serialise_in_investigation_json(self):
        spec = load_spec(SPEC_CA)
        case = _case(
            case_id="c1",
            sum_amount=Decimal("12345.67"),
            window_end=datetime(2026, 4, 15),
        )
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            payload = json.loads(zf.read("investigation.json"))
        assert "12345.67" in str(payload["total_amount"])

    def test_bundle_hash_helper_hashes_full_zip(self):
        import hashlib

        spec = load_spec(SPEC_CA)
        case = _case(case_id="c1", window_end=datetime(2026, 4, 15))
        invs = aggregate_investigations([case])
        bundle = bundle_investigation_to_str(
            invs[0],
            cases=[case],
            spec=spec,
            customers=[_customer()],
            transactions=[],
        )
        assert bundle_hash(bundle) == hashlib.sha256(bundle).hexdigest()


# ---------------------------------------------------------------------------
# End-to-end with engine output
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_bundles_real_engine_investigation(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        run_spec(
            spec=spec,
            spec_path=SPEC_CA,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        cases_dirs = list(tmp_path.glob("**/cases"))
        cases = [json.loads(f.read_text()) for f in sorted(cases_dirs[0].glob("*.json"))]
        invs = aggregate_investigations(cases)
        assert invs, "engine run should have produced at least one investigation"

        # Bundle the first investigation's cases.
        first = invs[0]
        constituent = [c for c in cases if c.get("case_id") in first["case_ids"]]
        bundle = bundle_investigation_to_str(
            first,
            cases=constituent,
            spec=spec,
            customers=data["customer"],
            transactions=data["txn"],
        )
        # Bundle parses, contains expected files, manifest hashes verify.
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            assert zf.testzip() is None
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["case_count"] == len(first["case_ids"])
            assert manifest["jurisdiction"] == "CA"
        # Round-trip determinism: bundling again yields identical bytes.
        bundle2 = bundle_investigation_to_str(
            first,
            cases=constituent,
            spec=spec,
            customers=data["customer"],
            transactions=data["txn"],
        )
        assert bundle == bundle2
