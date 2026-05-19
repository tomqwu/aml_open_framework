"""Source guards for the PR-U2 Knowledge section.

PR-U2 of the unified-product epic ports the 8 GitHub-Pages Research
whitepapers into native Streamlit Knowledge pages. The pages are
Streamlit scripts (run by Streamlit, never imported by unit tests), so
the live render is covered by the Playwright e2e. These fast file-text
+ data-module guards pin that the Knowledge nav category, the 8 ported
pages, the generated prose substrate, and the universal audience
routing exist and don't silently regress — same pattern as
test_dashboard_data_integration_pr_c.py / test_dashboard_dark_theme.py.

The generated substrate (`dashboard/data/research.py`) is import-safe
on the unit-test CI image (no streamlit) because its only streamlit
use is a lazy import INSIDE `render_body()` — asserted here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aml_framework.dashboard.audience import AUDIENCE_PAGES, KNOWLEDGE_PAGES, MAX_PAGES_PER_PERSONA
from aml_framework.dashboard.data import research

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "src" / "aml_framework" / "dashboard" / "pages"
APP = ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
AUDIENCE = ROOT / "src" / "aml_framework" / "dashboard" / "audience.py"
DATA = ROOT / "src" / "aml_framework" / "dashboard" / "data" / "research.py"
TOUR = ROOT / "docs" / "dashboard-tour.md"
EXTRACTOR = ROOT / "scripts" / "extract_research_markdown.py"

# slug -> (page_no, on-disk filename, nav title). The single source of
# truth this test pins the whole feature against.
EXPECTED = {
    "architecture": (33, "33_Knowledge_Architecture.py", "Architecture"),
    "competitive-positioning": (
        34,
        "34_Knowledge_Competitive_Landscape.py",
        "Competitive Landscape",
    ),
    "data-problem": (35, "35_Knowledge_Data_Is_The_Problem.py", "Data Is The Problem"),
    "fintech": (36, "36_Knowledge_FinTech_AML_Reality.py", "FinTech AML Reality"),
    "lineage": (37, "37_Knowledge_Lineage_Deep_Dive.py", "Lineage Deep-Dive"),
    "process-pain": (38, "38_Knowledge_AML_Process_Pain.py", "AML Process Pain"),
    "regulator-pulse": (39, "39_Knowledge_Regulator_Pulse_Brief.py", "Regulator Pulse Brief"),
    "td-2024": (40, "40_Knowledge_TD_2024_Case_Study.py", "TD 2024 Case Study"),
}


class TestResearchSubstrate:
    def test_eight_whitepapers_present(self):
        assert set(research.WHITEPAPERS) == set(EXPECTED)

    def test_each_record_has_substantive_prose(self):
        for slug, wp in research.WHITEPAPERS.items():
            # The extractor strips chrome; a few-hundred-char floor
            # catches a regression that silently empties a page.
            assert len(wp["body_md"]) > 1500, f"{slug} body suspiciously short"
            assert wp["nav_title"], slug
            assert wp["gh_source"].endswith(".md"), slug

    def test_nav_metadata_matches_expected(self):
        for slug, (page_no, _fname, nav_title) in EXPECTED.items():
            wp = research.WHITEPAPERS[slug]
            assert wp["page_no"] == page_no, slug
            assert wp["nav_title"] == nav_title, slug

    def test_balanced_markdown_emphasis(self):
        # The HTML→MD extractor's structural inline model must never
        # emit unbalanced ** or ` (the bug class the rewrite fixed).
        for slug, wp in research.WHITEPAPERS.items():
            for ln in wp["body_md"].splitlines():
                assert ln.count("**") % 2 == 0, f"{slug}: odd ** in {ln!r}"
                assert ln.count("`") % 2 == 0, f"{slug}: odd backtick in {ln!r}"

    def test_render_body_is_lazy_streamlit(self):
        # Module-level import of streamlit would break unit-test CI
        # (only `.[dev]` installed). The streamlit import must live
        # INSIDE render_body, mirroring audience.py / data_layer.py.
        tree = ast.parse(DATA.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                names = [a.name for a in node.names]
                assert "streamlit" not in mod and "streamlit" not in names, (
                    "research.py must not import streamlit at module level"
                )
        fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_body"
        )
        src = ast.get_source_segment(DATA.read_text(encoding="utf-8"), fn)
        assert "import streamlit" in src, "render_body must lazily import streamlit"


class TestKnowledgePageFiles:
    def test_all_eight_page_files_exist(self):
        for _slug, (_no, fname, _t) in EXPECTED.items():
            assert (PAGES_DIR / fname).is_file(), f"missing page file {fname}"

    def test_each_page_has_literal_page_header_and_delegates(self):
        # The literal page_header(title, ...) satisfies the title-mining
        # contract in test_dashboard_workflows.py; the body delegates to
        # the shared substrate so no prose is copy-pasted into pages.
        for slug, (_no, fname, nav_title) in EXPECTED.items():
            body = (PAGES_DIR / fname).read_text(encoding="utf-8")
            assert f'page_header("{nav_title}"' in body, f"{fname} title drift"
            assert f'research.render_body("{slug}")' in body, f"{fname} not delegating"

    def test_each_page_is_direct_url_robust_and_explained(self):
        # Mirrors 27_Regulator_Pulse.py: ensure_initialized() for
        # bookmark/pod-restart robustness + a page-level
        # section_explainer with a literal section_id (the "GenAI on
        # every page" promise + stable audit/cache key).
        for _slug, (_no, fname, nav_title) in EXPECTED.items():
            body = (PAGES_DIR / fname).read_text(encoding="utf-8")
            assert "ensure_initialized()" in body, f"{fname} missing init guard"
            assert "section_explainer(" in body, f"{fname} missing explainer"
            assert 'section_id="knowledge_' in body, f"{fname} section_id drift"


class TestKnowledgeNavWiring:
    def test_app_has_knowledge_category(self):
        body = APP.read_text(encoding="utf-8")
        assert '"Knowledge": [' in body, "app.py missing the Knowledge nav category"
        for _slug, (_no, fname, _t) in EXPECTED.items():
            assert fname in body, f"{fname} not registered in app.py ALL_PAGES"

    def test_knowledge_after_operational_categories(self):
        body = APP.read_text(encoding="utf-8")
        # Reference shelf sits after the day-to-day surfaces.
        assert body.index('"Operations": [') < body.index('"Knowledge": [')
        assert body.index('"FinTech": [') < body.index('"Knowledge": [')

    def test_knowledge_pages_routed_universally(self):
        body = APP.read_text(encoding="utf-8")
        # Universal idiom: added to every persona's visible set, same
        # as Today / Executive Dashboard — never gated by AUDIENCE_PAGES.
        assert "relevant_titles.update(KNOWLEDGE_PAGES)" in body

    def test_knowledge_pages_constant_matches_nav_titles(self):
        assert KNOWLEDGE_PAGES == [
            research.WHITEPAPERS[s]["nav_title"] for s in research.WHITEPAPERS
        ]

    def test_knowledge_not_in_audience_pages(self):
        # Keeping Knowledge OUT of AUDIENCE_PAGES is what preserves the
        # per-persona operational cap; it's universal, not role-routed.
        for persona, pages in AUDIENCE_PAGES.items():
            for kp in KNOWLEDGE_PAGES:
                assert kp not in pages, (
                    f"{kp!r} leaked into AUDIENCE_PAGES[{persona!r}] — would "
                    f"count against MAX_PAGES_PER_PERSONA={MAX_PAGES_PER_PERSONA}"
                )


class TestKnowledgeTourCoverage:
    def test_tour_has_knowledge_section_and_headings(self):
        body = TOUR.read_text(encoding="utf-8")
        assert "## Knowledge Pages" in body
        # The tour-coverage test derives "Knowledge <Name>" from the
        # filename; pin those exact headings here too.
        for _slug, (_no, fname, _t) in EXPECTED.items():
            derived = fname.removesuffix(".py").partition("_")[2].replace("_", " ")
            assert f"### {derived}\n" in body, f"tour missing '### {derived}'"


@pytest.mark.skipif(
    not EXTRACTOR.exists(),
    reason="scripts/ not shipped in the slim runtime Docker image (docker-build job)",
)
class TestExtractorIdempotent:
    def test_extractor_is_lazy_and_stdlib_only(self):
        src = EXTRACTOR.read_text(encoding="utf-8")
        # No new runtime markdown-parser dependency; stdlib html.parser.
        assert "from html.parser import HTMLParser" in src
        assert "import mistune" not in src and "markdown_it" not in src
