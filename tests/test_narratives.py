"""Narrative drafter tests — models, template baseline, mocked LLM backends.

Network is forbidden in CI: Ollama and OpenAI backends are exercised by
patching their single `_call_*` HTTP function. The template backend is
the deterministic baseline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from aml_framework.narratives import (
    CaseEvidence,
    DraftedNarrative,
    NarrativeError,
    TemplateBackend,
    case_to_evidence,
    get_drafter,
    load_case_evidence_from_run_dir,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestCaseEvidence:
    def test_minimal_construct(self):
        ev = CaseEvidence(
            case_id="c1",
            rule_id="r",
            rule_name="rule",
            severity="high",
            queue="l1",
        )
        assert ev.case_id == "c1"
        assert ev.transactions == []
        assert ev.regulation_refs == []

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            CaseEvidence(
                case_id="c1",
                rule_id="r",
                rule_name="rule",
                severity="high",
                queue="l1",
                bogus="x",  # type: ignore[call-arg]
            )

    def test_frozen(self):
        ev = CaseEvidence(case_id="c1", rule_id="r", rule_name="x", severity="h", queue="l")
        with pytest.raises(Exception):
            ev.case_id = "c2"  # type: ignore[misc]


class TestDraftedNarrative:
    def test_confidence_must_be_in_range(self):
        with pytest.raises(Exception):
            DraftedNarrative(
                case_id="c1",
                narrative_text="x",
                confidence=1.5,
                drafted_by="t",
            )

    def test_recommended_action_enum(self):
        with pytest.raises(Exception):
            DraftedNarrative(
                case_id="c1",
                narrative_text="x",
                confidence=0.5,
                drafted_by="t",
                recommended_action="bogus",  # type: ignore[arg-type]
            )

    def test_default_drafted_at_set(self):
        d = DraftedNarrative(
            case_id="c1",
            narrative_text="x",
            confidence=0.5,
            drafted_by="t",
        )
        assert isinstance(d.drafted_at, datetime)


class TestCaseToEvidence:
    def test_round_trip_from_case_dict(self):
        case = {
            "case_id": "case-123",
            "rule_id": "structuring",
            "rule_name": "Cash structuring",
            "severity": "high",
            "queue": "l1",
            "spec_program": "schedule_i_bank",
            "alert": {
                "customer_id": "C0001",
                "sum_amount": "45900.00",
                "explanation": "scorer says high",
                "feature_attribution": {"velocity": 0.8},
            },
            "regulation_refs": [{"citation": "PCMLTFA s.11", "description": "x"}],
        }
        cust = {"customer_id": "C0001", "full_name": "Olena K"}
        txns = [{"customer_id": "C0001", "amount": "9500", "booked_at": "2026-04-10"}]

        ev = case_to_evidence(case, cust, txns, jurisdiction="CA")
        assert ev.case_id == "case-123"
        assert ev.customer == cust
        assert len(ev.transactions) == 1
        assert ev.feature_attribution == {"velocity": 0.8}
        assert ev.explanation == "scorer says high"
        assert ev.jurisdiction == "CA"


# ---------------------------------------------------------------------------
# Template backend
# ---------------------------------------------------------------------------


def _evidence(severity="high"):
    return CaseEvidence(
        case_id="case-1",
        rule_id="structuring_cash_deposits",
        rule_name="Cash structuring",
        severity=severity,
        queue="l1",
        spec_program="schedule_i_bank",
        jurisdiction="CA",
        customer={"customer_id": "C0001", "full_name": "Olena K", "country": "CA"},
        alert={
            "customer_id": "C0001",
            "sum_amount": "45900.00",
            "count": 5,
            "window_start": "2026-04-05 23:00:00",
            "window_end": "2026-04-25 03:00:00",
        },
        transactions=[
            {"customer_id": "C0001", "amount": "9500", "channel": "cash"},
            {"customer_id": "C0001", "amount": "9800", "channel": "cash"},
        ],
        regulation_refs=[{"citation": "PCMLTFA s.11.1", "description": "Structuring offence."}],
    )


class TestTemplateBackend:
    def test_produces_valid_drafted_narrative(self):
        result = TemplateBackend().draft(_evidence())
        assert isinstance(result, DraftedNarrative)
        assert result.case_id == "case-1"

    def test_includes_citation_from_regulation_refs(self):
        result = TemplateBackend().draft(_evidence())
        assert any(c.citation == "PCMLTFA s.11.1" for c in result.citations)

    def test_severity_drives_recommended_action(self):
        assert TemplateBackend().draft(_evidence("critical")).recommended_action == "file_str"
        assert TemplateBackend().draft(_evidence("low")).recommended_action == "close_no_action"

    def test_findings_contain_amount_and_window(self):
        findings = " | ".join(TemplateBackend().draft(_evidence()).key_findings)
        assert "45900.00" in findings
        assert "2026-04-05" in findings

    def test_drafted_by_label(self):
        result = TemplateBackend().draft(_evidence())
        assert result.drafted_by == "template:v1"

    def test_deterministic_with_pinned_now(self):
        now = datetime(2026, 4, 27, tzinfo=timezone.utc)
        a = TemplateBackend(_now=now).draft(_evidence())
        b = TemplateBackend(_now=now).draft(_evidence())
        assert a == b

    def test_no_citations_when_no_refs(self):
        ev = CaseEvidence(case_id="c", rule_id="r", rule_name="x", severity="medium", queue="l")
        assert TemplateBackend().draft(ev).citations == []


# ---------------------------------------------------------------------------
# Ollama backend (mocked HTTP)
# ---------------------------------------------------------------------------


class TestOllamaBackend:
    def test_happy_path_returns_validated_narrative(self):
        from aml_framework.narratives.ollama import OllamaBackend

        fake_response = {
            "response": json.dumps(
                {
                    "case_id": "case-1",
                    "narrative_text": "Customer made 5 cash deposits below CTR threshold.",
                    "key_findings": ["Five deposits in 20 days"],
                    "citations": [
                        {
                            "rule_id": "structuring_cash_deposits",
                            "citation": "PCMLTFA s.11.1",
                            "claim": "Structuring offence",
                        }
                    ],
                    "recommended_action": "file_str",
                    "confidence": 0.82,
                }
            )
        }
        with mock.patch("aml_framework.narratives.ollama._call_ollama", return_value=fake_response):
            backend = OllamaBackend(model="llama3.1:8b")
            result = backend.draft(_evidence())

        assert result.case_id == "case-1"
        assert result.recommended_action == "file_str"
        assert result.drafted_by == "ollama:llama3.1:8b"
        assert any(c.citation == "PCMLTFA s.11.1" for c in result.citations)

    def test_missing_optional_fields_get_defaults(self):
        from aml_framework.narratives.ollama import OllamaBackend

        # Model returned only the bare minimum.
        fake = {"response": json.dumps({"narrative_text": "Short draft.", "confidence": 0.4})}
        with mock.patch("aml_framework.narratives.ollama._call_ollama", return_value=fake):
            result = OllamaBackend().draft(_evidence())
        assert result.narrative_text == "Short draft."
        assert result.recommended_action == "investigate_further"  # default
        assert result.citations == []

    def test_non_json_body_raises_narrative_error(self):
        from aml_framework.narratives.ollama import OllamaBackend

        with (
            mock.patch(
                "aml_framework.narratives.ollama._call_ollama",
                return_value={"response": "<html>oops</html>"},
            ),
            pytest.raises(NarrativeError, match="non-JSON"),
        ):
            OllamaBackend().draft(_evidence())

    def test_empty_body_raises_narrative_error(self):
        from aml_framework.narratives.ollama import OllamaBackend

        with (
            mock.patch(
                "aml_framework.narratives.ollama._call_ollama", return_value={"response": ""}
            ),
            pytest.raises(NarrativeError, match="empty"),
        ):
            OllamaBackend().draft(_evidence())

    def test_schema_violation_raises_narrative_error(self):
        from aml_framework.narratives.ollama import OllamaBackend

        # confidence outside [0,1] should fail schema validation.
        bad = {"response": json.dumps({"narrative_text": "x", "confidence": 5.0})}
        with (
            mock.patch("aml_framework.narratives.ollama._call_ollama", return_value=bad),
            pytest.raises(NarrativeError, match="schema"),
        ):
            OllamaBackend().draft(_evidence())


# ---------------------------------------------------------------------------
# OpenAI backend (mocked HTTP)
# ---------------------------------------------------------------------------


class TestOpenAIBackend:
    def test_refuses_without_api_key(self, monkeypatch):
        from aml_framework.narratives.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(NarrativeError, match="OPENAI_API_KEY"):
            OpenAIBackend()

    def test_constructor_arg_overrides_env(self, monkeypatch):
        from aml_framework.narratives.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = OpenAIBackend(api_key="sk-test")
        assert backend.api_key == "sk-test"

    def test_happy_path_with_mocked_call(self, monkeypatch):
        from aml_framework.narratives.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "narrative_text": "Suspicious cash structuring.",
                                "key_findings": [],
                                "citations": [],
                                "recommended_action": "file_str",
                                "confidence": 0.9,
                            }
                        )
                    }
                }
            ]
        }
        with mock.patch("aml_framework.narratives.openai._call_openai", return_value=fake_response):
            result = OpenAIBackend(model="gpt-4o-mini").draft(_evidence())
        assert result.recommended_action == "file_str"
        assert result.drafted_by == "openai:gpt-4o-mini"

    def test_unexpected_response_shape_raises(self, monkeypatch):
        from aml_framework.narratives.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with (
            mock.patch(
                "aml_framework.narratives.openai._call_openai", return_value={"choices": []}
            ),
            pytest.raises(NarrativeError, match="response shape"),
        ):
            OpenAIBackend().draft(_evidence())


# ---------------------------------------------------------------------------
# Factory + error paths
# ---------------------------------------------------------------------------


class TestGetDrafter:
    def test_template_default(self):
        d = get_drafter()
        assert d.name == "template:v1"

    def test_unknown_backend_raises(self):
        with pytest.raises(NarrativeError, match="Unknown drafter"):
            get_drafter("bogus")

    def test_ollama_factory(self):
        d = get_drafter("ollama")
        assert d.name.startswith("ollama:")

    def test_openai_factory_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(NarrativeError, match="OPENAI_API_KEY"):
            get_drafter("openai")


# ---------------------------------------------------------------------------
# Loader from run dir
# ---------------------------------------------------------------------------


class TestLoadFromRunDir:
    def test_round_trip_through_run_dir(self, tmp_path):
        run = tmp_path / "run-1"
        (run / "cases").mkdir(parents=True)
        case_path = run / "cases" / "case-1.json"
        case_path.write_text(
            json.dumps(
                {
                    "case_id": "case-1",
                    "rule_id": "structuring",
                    "rule_name": "Cash structuring",
                    "severity": "high",
                    "queue": "l1",
                    "alert": {
                        "customer_id": "C0001",
                        "window_start": "2026-04-01",
                        "window_end": "2026-04-30",
                    },
                    "regulation_refs": [],
                }
            )
        )
        ev = load_case_evidence_from_run_dir(
            run,
            "case-1",
            customers=[{"customer_id": "C0001", "full_name": "Test"}],
            transactions=[
                {"customer_id": "C0001", "amount": "1", "booked_at": "2026-04-10"},
                {"customer_id": "C0002", "amount": "2", "booked_at": "2026-04-10"},
            ],
        )
        assert ev.customer["customer_id"] == "C0001"
        # Only the C0001 txn should be filtered in.
        assert len(ev.transactions) == 1

    def test_missing_case_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_case_evidence_from_run_dir(tmp_path, "nope", [], [])
