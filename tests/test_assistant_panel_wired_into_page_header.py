"""Source-level tests pinning that PR-K wires the assistant panel into
every page via the shared `page_header()` helper.

The "AI assistant on every menu" requirement is satisfied by ONE call
inside `page_header()`. If a future refactor moves it out, this test
fails immediately rather than silently dropping the panel from N pages.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


def _page_header_body() -> str:
    """Return the body of the `page_header(...)` function definition."""
    body = COMPONENTS.read_text(encoding="utf-8")
    start = body.index("def page_header(")
    end = body.index("\ndef ", start + 1)
    return body[start:end]


class TestPageHeaderMountsAssistant:
    def test_page_header_calls_ai_panel(self):
        fn = _page_header_body()
        assert "ai_panel(" in fn, (
            "page_header() must invoke ai_panel() — that single call is what "
            "puts the GenAI co-pilot on every dashboard page (PR-K)."
        )

    def test_ai_panel_call_is_inside_try_block(self):
        """The assistant must NEVER crash a page render. The call must
        be wrapped in try/except so a misconfigured backend doesn't
        black out the dashboard."""
        fn = _page_header_body()
        try_idx = fn.find("try:")
        ai_idx = fn.find("ai_panel(")
        assert try_idx > 0 and ai_idx > try_idx, (
            "ai_panel(...) must be inside a try/except inside page_header()"
        )


class TestAiPanelHelperContract:
    """The helper itself has commitments operators rely on."""

    def test_ai_panel_function_defined(self):
        body = COMPONENTS.read_text(encoding="utf-8")
        assert "def ai_panel(" in body

    def test_ai_panel_keys_widgets_per_page(self):
        """Streamlit re-renders on interaction. Without a per-page key,
        navigating between pages would reset the textarea state from
        every page. Pin that the panel scopes its widget keys.
        Accepts the key as either an inline f-string in the widget call
        or as a hoisted variable like `question_key = f"ai_question_{page}"`."""
        body = COMPONENTS.read_text(encoding="utf-8")
        assert 'f"ai_question_{page}"' in body, (
            "Textarea key must be page-scoped (f\"ai_question_{page}\")"
        )
        assert 'f"ai_ask_{page}"' in body, (
            "Submit button key must be page-scoped (f\"ai_ask_{page}\")"
        )

    def test_ai_panel_reads_AML_AI_BACKEND_env(self):
        body = COMPONENTS.read_text(encoding="utf-8")
        assert 'os.environ.get("AML_AI_BACKEND"' in body, (
            "Backend selection must come from AML_AI_BACKEND env var, not hardcoded"
        )

    def test_openai_pii_banner_present(self):
        body = COMPONENTS.read_text(encoding="utf-8")
        # Operator must be warned BEFORE submitting that data may transit.
        assert "PII" in body and "OpenAI" in body

    def test_audit_log_uses_ai_interactions_jsonl(self):
        body = COMPONENTS.read_text(encoding="utf-8")
        assert 'jsonl_name="ai_interactions.jsonl"' in body, (
            "AI interactions must NOT mix into decisions.jsonl — they live "
            "in their own append-only log so audit pipelines can query them "
            "separately"
        )

    def test_full_text_vs_hash_only_dispatch(self):
        body = COMPONENTS.read_text(encoding="utf-8")
        assert 'audit_mode == "full_text"' in body, (
            "Spec's program.ai_audit_log flag must drive the full_text vs "
            "hash_only decision — institutions opt into full_text via the spec"
        )


class TestProgramSpecHasAiAuditLogField:
    """The spec schema must accept program.ai_audit_log."""

    def test_pydantic_model_has_field(self):
        from aml_framework.spec.models import Program

        # Pydantic v2 records fields on .model_fields
        assert "ai_audit_log" in Program.model_fields
        # Default is hash_only — privacy by default.
        default = Program.model_fields["ai_audit_log"].default
        assert default == "hash_only"

    def test_jsonschema_has_field(self):
        schema_path = PROJECT_ROOT / "schema" / "aml-spec.schema.json"
        body = schema_path.read_text(encoding="utf-8")
        # Match the property block + enum
        m = re.search(r'"ai_audit_log"\s*:\s*\{[^}]+\}', body)
        assert m, "schema/aml-spec.schema.json must declare ai_audit_log"
        block = m.group(0)
        assert "hash_only" in block and "full_text" in block, "schema must pin the two valid values"


class TestAudienceRouting:
    def test_ai_assistant_in_senior_persona_lists(self):
        body = (PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "audience.py").read_text(
            encoding="utf-8"
        )
        # 5 senior personas should land here per the plan
        for persona in ("cco", "vp", "auditor", "developer", "fintech_mlro"):
            block_start = body.find(f'"{persona}": [')
            assert block_start > 0
            block = body[block_start : block_start + 900]
            assert "AI Assistant" in block, (
                f"persona '{persona}' must include 'AI Assistant' in their pages"
            )

    def test_ai_assistant_NOT_in_analyst_list(self):
        body = (PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "audience.py").read_text(
            encoding="utf-8"
        )
        analyst_start = body.find('"analyst": [')
        block = body[analyst_start : analyst_start + 500]
        # Analysts use the inline panel; they shouldn't be routed to the
        # audit-trail-shaped #29 page (it's for senior personas only).
        assert "AI Assistant" not in block


class TestAiAssistantPageExists:
    def test_page_file_exists(self):
        path = PAGES_DIR / "29_AI_Assistant.py"
        assert path.exists(), "PR-K must add 29_AI_Assistant.py"

    def test_page_calls_page_header(self):
        body = (PAGES_DIR / "29_AI_Assistant.py").read_text(encoding="utf-8")
        assert "page_header(" in body
        assert "AI Assistant" in body
