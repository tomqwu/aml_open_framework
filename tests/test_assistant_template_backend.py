"""Behaviour tests for the GenAI Assistant's template backend (PR-K).

The template backend is the default — it must work without any
optional deps, return a valid `AssistantReply`, and never make a
network call. These tests pin those invariants.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from aml_framework.assistant import (
    Assistant,
    AssistantContext,
    AssistantError,
    AssistantReply,
    TemplateBackend,
    get_assistant,
)
from aml_framework.assistant.models import reply_to_audit_dict


class TestTemplateBackendBasics:
    def test_factory_returns_template_by_default(self):
        backend = get_assistant()
        assert isinstance(backend, Assistant)
        assert backend.name.startswith("template")

    def test_factory_explicit_template(self):
        backend = get_assistant("template")
        assert isinstance(backend, TemplateBackend)
        assert backend.name == "template:v1"

    def test_reply_is_valid_AssistantReply(self):
        backend = TemplateBackend()
        ctx = AssistantContext(
            page="Executive Dashboard",
            persona="cco",
            spec_name="Test Bank",
            rule_count=12,
            metric_count=8,
        )
        reply = backend.reply("why is alert volume high?", ctx)
        assert isinstance(reply, AssistantReply)
        assert reply.text  # non-empty
        assert reply.backend == "template:v1"
        assert reply.prompted_with_page == "Executive Dashboard"
        assert reply.prompted_with_persona == "cco"
        assert reply.confidence in {"high", "medium", "low"}

    def test_reply_echoes_question_back(self):
        backend = TemplateBackend()
        ctx = AssistantContext(page="Run History")
        reply = backend.reply("how do I tune this rule?", ctx)
        # The template backend acknowledges the question so the operator
        # sees the panel is reaching them. This is part of the canned
        # scaffolding contract — replies aren't useful but they are present.
        assert (
            "how do I tune this rule" in reply.text.lower()
            or "how do i tune this rule" in reply.text.lower()
        )

    def test_reply_picks_up_deep_link_focus(self):
        backend = TemplateBackend()
        ctx = AssistantContext(
            page="Case Investigation",
            selected_case_id="CASE-2026-04-001",
        )
        reply = backend.reply("draft me an STR", ctx)
        assert "CASE-2026-04-001" in reply.referenced_case_ids
        # Focused-on-case line surfaces in the body too.
        assert "CASE-2026-04-001" in reply.text

    def test_focus_line_covers_other_deep_link_entities(self):
        assert "customer: `C-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Customer 360", selected_customer_id="C-1")
        )
        assert "rule: `R-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Rules", selected_rule_id="R-1")
        )
        assert "metric: `M-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Metrics", selected_metric_id="M-1")
        )
        assert TemplateBackend._focus_line(AssistantContext(page="Executive Dashboard")) == ""


class TestAuditDict:
    def test_hash_only_mode_omits_full_text(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Risk Assessment", persona="cco")
        reply = backend.reply("how risky is this portfolio?", ctx)
        row = reply_to_audit_dict(reply, full_text=False)
        assert "reply_text" not in row
        assert "reply_text_hash" in row
        assert len(row["reply_text_hash"]) == 64  # sha-256 hex

    def test_full_text_mode_logs_complete_reply(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Risk Assessment", persona="cco")
        reply = backend.reply("explain to me", ctx)
        row = reply_to_audit_dict(reply, full_text=True)
        assert "reply_text" in row
        assert row["reply_text"] == reply.text
        assert "reply_text_hash" not in row

    def test_audit_dict_carries_provenance(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Audit & Evidence", persona="auditor")
        reply = backend.reply("when was this run finalised?", ctx)
        row = reply_to_audit_dict(reply, full_text=False)
        assert row["page"] == "Audit & Evidence"
        assert row["persona"] == "auditor"
        assert row["backend"] == "template:v1"
        assert row["confidence"] in {"high", "medium", "low"}
        assert isinstance(row["citations"], list)


class TestFactoryEnvLookup:
    def test_factory_reads_AML_AI_BACKEND_env(self, monkeypatch):
        monkeypatch.setenv("AML_AI_BACKEND", "template")
        backend = get_assistant()
        assert backend.name.startswith("template")

    def test_factory_unknown_backend_raises(self):
        try:
            get_assistant("not_a_real_backend")
        except AssistantError as e:
            assert "not_a_real_backend" in str(e)
        else:
            raise AssertionError("expected AssistantError")

    def test_factory_returns_ollama_backend(self):
        backend = get_assistant("ollama", model="llama3.1:8b")
        assert backend.name == "ollama:llama3.1:8b"

    def test_factory_openai_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(AssistantError, match="OPENAI_API_KEY"):
            get_assistant("openai")


class TestAssistantOllamaBackend:
    def test_happy_path_returns_validated_reply(self):
        from aml_framework.assistant.ollama import OllamaBackend

        fake_response = {
            "response": json.dumps(
                {
                    "text": "Alert volume is concentrated in case CASE-1.",
                    "confidence": "high",
                    "referenced_metric_ids": ["metric-alert-volume"],
                    "referenced_case_ids": ["CASE-1"],
                    "referenced_customer_ids": ["C-1"],
                    "citations": [
                        {
                            "rule_id": "structuring_cash_deposits",
                            "citation": "PCMLTFA s.11.1",
                            "claim": "Structuring typology",
                        }
                    ],
                }
            )
        }
        ctx = AssistantContext(page="Executive Dashboard", persona="cco")
        with mock.patch("aml_framework.assistant.ollama._call_ollama", return_value=fake_response):
            reply = OllamaBackend(model="llama3.1:8b").reply("why is volume high?", ctx)

        assert reply.text.startswith("Alert volume")
        assert reply.backend == "ollama:llama3.1:8b"
        assert reply.confidence == "high"
        assert reply.referenced_metric_ids == ["metric-alert-volume"]
        assert reply.referenced_case_ids == ["CASE-1"]
        assert reply.referenced_customer_ids == ["C-1"]
        assert reply.citations[0].citation == "PCMLTFA s.11.1"

    def test_missing_optional_fields_get_defaults(self):
        from aml_framework.assistant.ollama import OllamaBackend

        fake = {"response": json.dumps({"text": "Short answer.", "confidence": "certain"})}
        with mock.patch("aml_framework.assistant.ollama._call_ollama", return_value=fake):
            reply = OllamaBackend().reply("summarize", AssistantContext(page="Run History"))

        assert reply.text == "Short answer."
        assert reply.confidence == "low"
        assert reply.citations == []
        assert reply.referenced_metric_ids == []

    def test_invalid_citations_are_ignored(self):
        from aml_framework.assistant.ollama import _build_reply

        reply = _build_reply(
            {
                "text": "Answer",
                "citations": [
                    "not a citation",
                    {"rule_id": "r1", "citation": "ref", "claim": "claim"},
                    {"rule_id": 1, "citation": [], "claim": {}},
                ],
            },
            AssistantContext(page="Case Investigation", persona="analyst"),
            backend="test",
        )

        assert len(reply.citations) == 1
        assert reply.citations[0].rule_id == "r1"

    def test_unexpected_response_shape_raises(self):
        from aml_framework.assistant.ollama import OllamaBackend

        with (
            mock.patch("aml_framework.assistant.ollama._call_ollama", return_value={}),
            pytest.raises(AssistantError, match="response shape"),
        ):
            OllamaBackend().reply("hello", AssistantContext(page="Today"))

    def test_non_json_response_raises(self):
        from aml_framework.assistant.ollama import OllamaBackend

        with (
            mock.patch(
                "aml_framework.assistant.ollama._call_ollama",
                return_value={"response": "<html>oops</html>"},
            ),
            pytest.raises(AssistantError, match="non-JSON"),
        ):
            OllamaBackend().reply("hello", AssistantContext(page="Today"))


class TestAssistantOpenAIBackend:
    def test_refuses_without_api_key(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(AssistantError, match="OPENAI_API_KEY"):
            OpenAIBackend()

    def test_constructor_arg_overrides_env(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = OpenAIBackend(api_key="sk-test", model="gpt-test")
        assert backend.api_key == "sk-test"
        assert backend.name == "openai:gpt-test"

    def test_happy_path_with_mocked_call(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "text": "Use the case queue trend.",
                                "confidence": "medium",
                                "referenced_case_ids": ["CASE-9"],
                            }
                        )
                    }
                }
            ]
        }
        with mock.patch("aml_framework.assistant.openai._call_openai", return_value=fake_response):
            reply = OpenAIBackend(model="gpt-4o-mini").reply(
                "what should I inspect?", AssistantContext(page="Case Queue")
            )

        assert reply.backend == "openai:gpt-4o-mini"
        assert reply.confidence == "medium"
        assert reply.referenced_case_ids == ["CASE-9"]

    def test_unexpected_response_shape_raises(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with (
            mock.patch("aml_framework.assistant.openai._call_openai", return_value={"choices": []}),
            pytest.raises(AssistantError, match="response shape"),
        ):
            OpenAIBackend().reply("hello", AssistantContext(page="Today"))

    def test_non_json_response_raises(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with (
            mock.patch(
                "aml_framework.assistant.openai._call_openai",
                return_value={"choices": [{"message": {"content": "not json"}}]},
            ),
            pytest.raises(AssistantError, match="non-JSON"),
        ):
            OpenAIBackend().reply("hello", AssistantContext(page="Today"))
