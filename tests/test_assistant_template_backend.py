"""Behaviour tests for the GenAI Assistant's template backend (PR-K).

The template backend is the default — it must work without any
optional deps, return a valid `AssistantReply`, and never make a
network call. These tests pin those invariants.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aml_framework.assistant import (
    Assistant,
    AssistantContext,
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
        from aml_framework.assistant import AssistantError

        try:
            get_assistant("not_a_real_backend")
        except AssistantError as e:
            assert "not_a_real_backend" in str(e)
        else:
            raise AssertionError("expected AssistantError")
