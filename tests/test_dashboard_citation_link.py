"""Source-level + behaviour tests for PR-F: regulation citation hyperlinks.

Citations show as text but the underlying regulation URL is in the
spec (`regulation_refs[*].url`). PR-F adds a `citation_link(citation,
url)` helper to `components.py` and wires it through Rule Performance,
Audit & Evidence (drift table), Framework Alignment (control matrix),
and Case Investigation.

Mix of behavioural tests (the helper itself) and source-level grep
checks (the pages call it).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


def _load_citation_link():
    """Load just the citation_link function without importing streamlit.

    components.py imports streamlit at module level — the lint-only CI
    image doesn't have it installed. We compile + exec just the
    function definition in isolation.
    """
    body = COMPONENTS_FILE.read_text(encoding="utf-8")
    start = body.index("def citation_link(")
    end = body.index("\ndef ", start + 1)
    src = body[start:end]
    ns: dict = {}
    exec(src, ns)
    return ns["citation_link"]


class TestCitationLinkBehaviour:
    def test_returns_markdown_link_when_url_present(self):
        cl = _load_citation_link()
        assert cl("31 CFR 1020.320", "https://www.ecfr.gov/foo") == (
            "[31 CFR 1020.320](https://www.ecfr.gov/foo)"
        )

    def test_returns_plain_text_when_url_none(self):
        cl = _load_citation_link()
        assert cl("31 CFR 1020.320", None) == "31 CFR 1020.320"

    def test_returns_plain_text_when_url_empty(self):
        cl = _load_citation_link()
        assert cl("31 CFR 1020.320", "") == "31 CFR 1020.320"

    def test_returns_plain_text_when_url_whitespace(self):
        cl = _load_citation_link()
        assert cl("31 CFR 1020.320", "   ") == "31 CFR 1020.320"


class TestPagesUseCitationLink:
    def test_rule_performance_imports_helper(self):
        body = (PAGES_DIR / "5_Rule_Performance.py").read_text(encoding="utf-8")
        assert "citation_link" in body

    def test_case_investigation_imports_helper(self):
        body = (PAGES_DIR / "4_Case_Investigation.py").read_text(encoding="utf-8")
        assert "citation_link" in body

    def test_audit_evidence_imports_helper(self):
        body = (PAGES_DIR / "7_Audit_Evidence.py").read_text(encoding="utf-8")
        assert "citation_link" in body

    def test_framework_alignment_imports_helper(self):
        body = (PAGES_DIR / "8_Framework_Alignment.py").read_text(encoding="utf-8")
        assert "citation_link" in body
