"""PSD3 / VoP adapter tests — Round-7 PR #4.

Verifies the VoP response parser handles the 5 outcomes, both
camelCase + snake_case field variants, malformed input (no exceptions),
and bulk loader determinism.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aml_framework.data.psd3 import (
    VOP_OUTCOMES,
    VOP_SCHEMA_VERSION,
    load_vop_dir,
    parse_vop_response,
    vop_match_outcome,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VOP = PROJECT_ROOT / "src" / "aml_framework" / "data" / "psd3" / "sample_vop_responses.jsonl"


# ---------------------------------------------------------------------------
# vop_match_outcome — pure classifier
# ---------------------------------------------------------------------------


class TestVopMatchOutcome:
    def test_match_threshold_85(self):
        assert vop_match_outcome(score=0.95) == "match"
        assert vop_match_outcome(score=0.85) == "match"

    def test_close_match_70_to_84(self):
        assert vop_match_outcome(score=0.84) == "close_match"
        assert vop_match_outcome(score=0.70) == "close_match"

    def test_no_match_below_70(self):
        assert vop_match_outcome(score=0.50) == "no_match"
        assert vop_match_outcome(score=0.0) == "no_match"

    def test_payee_not_supported_yields_not_checked(self):
        assert vop_match_outcome(score=0.99, payee_supports_vop=False) == "not_checked"

    def test_outside_scope_short_circuits(self):
        # Even with a perfect score, outside_scope wins.
        assert vop_match_outcome(score=1.0, in_scope=False) == "outside_scope"

    def test_none_score_yields_not_checked(self):
        assert vop_match_outcome(score=None) == "not_checked"

    def test_outside_scope_takes_priority_over_unsupported(self):
        # If both flags are off, outside_scope wins.
        assert (
            vop_match_outcome(score=None, payee_supports_vop=False, in_scope=False)
            == "outside_scope"
        )


# ---------------------------------------------------------------------------
# parse_vop_response — robust to malformed input
# ---------------------------------------------------------------------------


class TestParseVopResponse:
    def test_explicit_outcome_field_used(self):
        payload = {
            "requestId": "X",
            "paymentId": "P",
            "payerIban": "DE89370400440532013000",
            "payeeIban": "FR1420041010050500013M02606",
            "payeeNameSupplied": "ACME",
            "payeeNameActual": "ACME",
            "matchScore": 1.0,
            "outcome": "match",
            "responseTimeMs": 100,
        }
        r = parse_vop_response(payload)
        assert r is not None
        assert r.outcome == "match"
        assert r.match_score == 1.0
        assert r.request_id == "X"

    def test_outcome_computed_when_missing(self):
        # No `outcome` field — derived from score.
        payload = {
            "requestId": "X",
            "paymentId": "P",
            "payerIban": "A",
            "payeeIban": "B",
            "payeeNameSupplied": "n",
            "payeeNameActual": "n",
            "matchScore": 0.75,
        }
        r = parse_vop_response(payload)
        assert r.outcome == "close_match"

    def test_snake_case_field_names_accepted(self):
        payload = {
            "request_id": "Y",
            "payment_id": "P",
            "payer_iban": "A",
            "payee_iban": "B",
            "payee_name_supplied": "n",
            "payee_name_actual": "n",
            "match_score": 0.95,
            "response_time_ms": 50,
        }
        r = parse_vop_response(payload)
        assert r.request_id == "Y"
        assert r.outcome == "match"

    def test_invalid_json_returns_none(self):
        assert parse_vop_response(b"{not json") is None

    def test_non_dict_payload_returns_none(self):
        assert parse_vop_response('"a string"') is None

    def test_garbage_type_returns_none(self):
        assert parse_vop_response(12345) is None  # type: ignore[arg-type]

    def test_invalid_score_handled_gracefully(self):
        payload = {
            "requestId": "X",
            "paymentId": "P",
            "payerIban": "A",
            "payeeIban": "B",
            "payeeNameSupplied": "n",
            "payeeNameActual": "n",
            "matchScore": "not-a-number",
        }
        r = parse_vop_response(payload)
        assert r is not None
        assert r.match_score == 0.0
        # Score wasn't parseable → outcome falls through to not_checked.
        assert r.outcome == "not_checked"

    def test_received_at_iso_parsed(self):
        payload = {
            "requestId": "X",
            "paymentId": "P",
            "payerIban": "A",
            "payeeIban": "B",
            "payeeNameSupplied": "n",
            "payeeNameActual": "n",
            "matchScore": 1.0,
            "receivedAt": "2026-04-27T10:15:32",
        }
        r = parse_vop_response(payload)
        assert r.received_at == datetime(2026, 4, 27, 10, 15, 32)

    def test_received_at_invalid_format_yields_none(self):
        payload = {
            "requestId": "X",
            "paymentId": "P",
            "payerIban": "A",
            "payeeIban": "B",
            "payeeNameSupplied": "n",
            "payeeNameActual": "n",
            "matchScore": 1.0,
            "receivedAt": "not-a-date",
        }
        r = parse_vop_response(payload)
        assert r.received_at is None

    def test_schema_version_pinned(self):
        r = parse_vop_response(
            {
                "requestId": "X",
                "paymentId": "P",
                "payerIban": "A",
                "payeeIban": "B",
                "payeeNameSupplied": "n",
                "payeeNameActual": "n",
                "matchScore": 1.0,
            }
        )
        assert r.schema_version == VOP_SCHEMA_VERSION
        assert "draft" in VOP_SCHEMA_VERSION  # explicit DRAFT marker

    def test_to_dict_serialises_datetime(self):
        r = parse_vop_response(
            {
                "requestId": "X",
                "paymentId": "P",
                "payerIban": "A",
                "payeeIban": "B",
                "payeeNameSupplied": "n",
                "payeeNameActual": "n",
                "matchScore": 1.0,
                "receivedAt": "2026-04-27T10:15:32",
            }
        )
        d = r.to_dict()
        assert d["received_at"] == "2026-04-27T10:15:32"


# ---------------------------------------------------------------------------
# Bundled sample
# ---------------------------------------------------------------------------


class TestBundledSample:
    def test_sample_loads(self):
        responses = load_vop_dir(SAMPLE_VOP.parent)
        assert len(responses) == 6

    def test_sample_covers_all_outcomes(self):
        responses = load_vop_dir(SAMPLE_VOP.parent)
        outcomes = {r.outcome for r in responses}
        # Sample exercises 4 of the 5 outcomes.
        assert "match" in outcomes
        assert "close_match" in outcomes
        assert "no_match" in outcomes
        assert "not_checked" in outcomes
        assert "outside_scope" in outcomes

    def test_sample_is_sorted_by_request_id(self):
        responses = load_vop_dir(SAMPLE_VOP.parent)
        ids = [r.request_id for r in responses]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Bulk loader robustness
# ---------------------------------------------------------------------------


class TestBulkLoader:
    def test_empty_dir_yields_empty_list(self, tmp_path):
        assert load_vop_dir(tmp_path) == []

    def test_skips_malformed_lines(self, tmp_path):
        f = tmp_path / "vop.jsonl"
        f.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "requestId": "GOOD",
                            "paymentId": "P",
                            "payerIban": "A",
                            "payeeIban": "B",
                            "payeeNameSupplied": "n",
                            "payeeNameActual": "n",
                            "matchScore": 1.0,
                        }
                    ),
                    "{ malformed",
                    "",
                    json.dumps(
                        {
                            "requestId": "ALSO_GOOD",
                            "paymentId": "P",
                            "payerIban": "A",
                            "payeeIban": "B",
                            "payeeNameSupplied": "n",
                            "payeeNameActual": "n",
                            "matchScore": 1.0,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        responses = load_vop_dir(tmp_path)
        assert len(responses) == 2
        assert {r.request_id for r in responses} == {"GOOD", "ALSO_GOOD"}


# ---------------------------------------------------------------------------
# VOP_OUTCOMES contract
# ---------------------------------------------------------------------------


class TestVopOutcomesContract:
    def test_exactly_five_outcomes(self):
        assert len(VOP_OUTCOMES) == 5

    def test_outcomes_are_uk_cop_compatible(self):
        # The UK APP-fraud spec uses confirmation_of_payee_status with
        # the same value vocabulary. This guard keeps both schemes
        # interoperable through the same `txn` column.
        for o in ("match", "close_match", "no_match", "not_checked"):
            assert o in VOP_OUTCOMES
