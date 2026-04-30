"""Source-level + behaviour tests for PR-H: spec element + ID linking sweep.

Plain-text IDs (case_ids in the decision log, rule_ids in Rule
Performance, investigation case_ids in the detail expander) had no
path to the page that owns them. PR-H adds an `id_link(id, page, param)`
helper and threads it through Audit & Evidence, Rule Performance,
and Investigations. Tuning Lab gains a deep-link reader so a click
on a rule_id pre-selects the rule.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


def _load_id_link():
    """Compile + exec just the id_link helper, dodging the streamlit import."""
    body = COMPONENTS_FILE.read_text(encoding="utf-8")
    start = body.index("def id_link(")
    end = body.index("\ndef ", start + 1)
    src = body[start:end]
    ns: dict = {}
    exec(src, ns)
    return ns["id_link"]


class TestIdLinkBehaviour:
    def test_renders_markdown_link(self):
        il = _load_id_link()
        assert il("C0001", "17_Customer_360", "customer_id") == (
            "[C0001](./17_Customer_360?customer_id=C0001)"
        )

    def test_works_for_case_id(self):
        il = _load_id_link()
        assert il("INV-2026-04-001", "4_Case_Investigation", "case_id") == (
            "[INV-2026-04-001](./4_Case_Investigation?case_id=INV-2026-04-001)"
        )


class TestPagesUseIdLink:
    def test_audit_evidence_imports_helper(self):
        body = (PAGES_DIR / "7_Audit_Evidence.py").read_text(encoding="utf-8")
        assert "id_link" in body
        # Quick-jump section must reference Case Investigation
        assert "4_Case_Investigation" in body, (
            "Audit Evidence's case_id quick-jumps must target Case Investigation"
        )

    def test_investigations_imports_helper(self):
        body = (PAGES_DIR / "24_Investigations.py").read_text(encoding="utf-8")
        assert "id_link" in body
        assert "Cases in this investigation" in body, (
            "Investigation detail must surface case_ids as a clickable bullet list"
        )

    def test_rule_performance_imports_helper(self):
        body = (PAGES_DIR / "5_Rule_Performance.py").read_text(encoding="utf-8")
        assert "id_link" in body
        # Tunable rules → Tuning Lab deep links
        assert "23_Tuning_Lab" in body
        assert "Tunable rules" in body


class TestTuningLabDeepLink:
    def test_consumes_rule_id_param(self):
        body = (PAGES_DIR / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        assert 'consume_param("rule_id")' in body, (
            "Tuning Lab must consume the rule_id deep-link param so a "
            "click from Rule Performance pre-selects the rule"
        )

    def test_default_rule_falls_back_to_first(self):
        body = (PAGES_DIR / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        assert "_default_rule_idx" in body
        assert "else 0" in body
