"""Tests for the FINOS Open Compliance adapter + OpenAPI doc.

Process invariants guarded:
- Envelope shape matches the OpenAPI contract — receiving FIs that
  validate against the published schema accept what we send.
- The evidence SHA-256 in the envelope matches the bundle bytes —
  receiving FI's verification step succeeds.
- SLA tier mapping matches the contract description so the
  `sla_deadline` we'd return as a receiver matches what the doc
  promises a sender.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from aml_framework.api.finos_compliance import (
    InstitutionRef,
    build_handoff_request,
    build_outcome,
    bundle_sha256,
    sla_deadline_for,
)

OPENAPI_DOC = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "aml_framework"
    / "api"
    / "openapi-compliance.yaml"
)


# ---------------------------------------------------------------------------
# OpenAPI doc — structural invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_doc() -> dict:
    return yaml.safe_load(OPENAPI_DOC.read_text())


def test_openapi_doc_loads_and_is_3_0_x(openapi_doc) -> None:
    assert openapi_doc["openapi"].startswith("3.")


def test_openapi_doc_has_four_handoff_endpoints(openapi_doc) -> None:
    paths = set(openapi_doc["paths"].keys())
    assert paths == {
        "/v1/cases/handoff",
        "/v1/cases/handoff/{handoff_id}",
        "/v1/cases/handoff/{handoff_id}/evidence",
        "/v1/cases/handoff/{handoff_id}/acknowledge",
    }


def test_openapi_doc_declares_required_schemas(openapi_doc) -> None:
    schemas = openapi_doc["components"]["schemas"]
    for name in (
        "HandoffRequest",
        "HandoffAck",
        "HandoffStatus",
        "HandoffOutcome",
        "InstitutionRef",
    ):
        assert name in schemas


def test_openapi_doc_declares_both_mtls_and_jwt(openapi_doc) -> None:
    schemes = openapi_doc["components"]["securitySchemes"]
    assert "mtls" in schemes and schemes["mtls"]["type"] == "mutualTLS"
    assert "bearerAuth" in schemes and schemes["bearerAuth"]["scheme"] == "bearer"


# ---------------------------------------------------------------------------
# Adapter — envelope shape matches contract
# ---------------------------------------------------------------------------


def _case() -> dict:
    return {
        "case_id": "C-1",
        "customer_id": "C0001",
        "rule_id": "ramp_up_then_drain_rtp",
        "alert": {
            "customer_id": "C0001",
            "counterparty_account": "ACCT-PEER-42",
            "counterparty_name": "Peer Bank Customer",
        },
    }


def _sender() -> InstitutionRef:
    return InstitutionRef(name="Acme Bank", country="US", lei="L" * 20)


def _receiver() -> InstitutionRef:
    return InstitutionRef(name="Peer Bank", country="DE", lei="P" * 20)


def test_handoff_envelope_carries_required_fields(openapi_doc) -> None:
    payload = b"evidence-bundle-bytes"
    envelope = build_handoff_request(
        external_handoff_id="H-1",
        sending_fi=_sender(),
        receiving_fi=_receiver(),
        case=_case(),
        evidence_zip=payload,
        typology="ramp_up_then_drain_rtp",
        urgency="elevated",
    )
    required = openapi_doc["components"]["schemas"]["HandoffRequest"]["required"]
    for field in required:
        assert field in envelope, f"envelope missing required field {field}"


def test_handoff_envelope_evidence_hash_matches_bytes() -> None:
    payload = b"evidence-bundle-bytes"
    envelope = build_handoff_request(
        external_handoff_id="H-1",
        sending_fi=_sender(),
        receiving_fi=_receiver(),
        case=_case(),
        evidence_zip=payload,
        typology="x",
    )
    assert envelope["evidence_sha256"] == hashlib.sha256(payload).hexdigest()


def test_handoff_subject_uses_counterparty_account_when_present() -> None:
    envelope = build_handoff_request(
        external_handoff_id="H-1",
        sending_fi=_sender(),
        receiving_fi=_receiver(),
        case=_case(),
        evidence_zip=b"",
        typology="x",
    )
    assert envelope["subject"]["identifier_type"] == "account_number"
    assert envelope["subject"]["identifier_value"] == "ACCT-PEER-42"


def test_handoff_falls_back_to_opaque_when_subject_missing() -> None:
    case = {"case_id": "C-2", "alert": {}}
    envelope = build_handoff_request(
        external_handoff_id="H-2",
        sending_fi=_sender(),
        receiving_fi=_receiver(),
        case=case,
        evidence_zip=b"",
        typology="x",
    )
    assert envelope["subject"]["identifier_type"] == "opaque"


# ---------------------------------------------------------------------------
# Outcome envelope
# ---------------------------------------------------------------------------


def test_outcome_envelope_minimum_fields() -> None:
    body = build_outcome(outcome="str_filed", decided_at=datetime(2026, 5, 1, 10, 0))
    assert body["outcome"] == "str_filed"
    assert body["decided_at"].startswith("2026-05-01T10:00")


def test_outcome_envelope_includes_optional_fields_when_provided() -> None:
    body = build_outcome(
        outcome="str_filed",
        decided_at=datetime(2026, 5, 1),
        regulator_reference="STR-2026-99",
        narrative_summary="Confirmed mule pattern; STR filed.",
    )
    assert body["regulator_reference"] == "STR-2026-99"
    assert "Confirmed" in body["narrative_summary"]


# ---------------------------------------------------------------------------
# SLA tier mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "urgency,expected_hours", [("routine", 24), ("elevated", 4), ("immediate", 1)]
)
def test_sla_deadline_matches_openapi_doc(urgency: str, expected_hours: int) -> None:
    accepted = datetime(2026, 4, 28, 12, 0)
    deadline = sla_deadline_for(urgency, accepted_at=accepted)
    assert (deadline - accepted) == timedelta(hours=expected_hours)


def test_bundle_sha256_helper_matches_stdlib() -> None:
    payload = b"hello world"
    assert bundle_sha256(payload) == hashlib.sha256(payload).hexdigest()
