"""Source-guards for the PR-NS-1 North-Star Pillar Coverage page.

The page itself is a Streamlit script (never imported by unit tests —
streamlit isn't installed on the unit-test CI image which only carries
`.[dev]`), so the live render is covered by Playwright e2e. These fast
file-text + AST guards pin that:

  * The page file exists at the expected path
    (``pages/43_North_Star_Coverage.py``).
  * The page does NOT import streamlit at module level (the lazy-
    import discipline that lets unit-test CI parse the file).
    Actually — the page DOES import streamlit at the top because it's
    a Streamlit script (same as every other page in pages/), not an
    imported module. The discipline that matters for pages/ is that
    the file PARSES under py_compile / ast.parse without crashing on
    import paths the unit-test CI can't resolve. The "lazy" discipline
    in CLAUDE.md applies to `audience.py` / `data_layer.py` /
    `state.py` (modules imported by tests), not to pages/.
  * The 8 north-star pillar names from the
    ``project_aml_north_star`` memory each appear in the page source
    (prevents accidentally shipping 7).
  * Every pillar card carries at least one ``st.page_link`` (prevents
    a prose-only card slipping through).
  * Registration is wired in ``app.py`` (page listed under "Strategy
    & Reporting") and ``audience.py`` (``NORTH_STAR_PAGES`` constant,
    universally routed).

Same pattern as ``test_dashboard_knowledge.py`` /
``test_dashboard_data_integration_pr_c.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from aml_framework.dashboard.audience import (
    AUDIENCE_PAGES,
    MAX_PAGES_PER_PERSONA,
    NORTH_STAR_PAGES,
)

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "src" / "aml_framework" / "dashboard" / "pages"
APP = ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
AUDIENCE = ROOT / "src" / "aml_framework" / "dashboard" / "audience.py"
PAGE = PAGES_DIR / "43_North_Star_Coverage.py"
NAV_TITLE = "North-Star Pillar Coverage"

# The 8 pillar short names verbatim from the user's
# `project_aml_north_star` memory. If a pillar is renamed in the
# memory, this list updates and the page must follow — guards against
# the page silently drifting out of sync with the north-star.
PILLAR_NAMES = [
    "Equivalence before optimization",
    "Evidence as a product",
    "Point-in-time correctness",
    "DQ + reconciliation + defect management",
    "Risk-based controls",
    "Alert lifecycle & explainability",
    "DS as governed augmentation",
    "Serve five roles",
]


class TestPageFile:
    def test_page_file_exists(self):
        # Source-guard #1 — the page lives where the registration
        # claims it does. A rename would break the Streamlit
        # st.Page("pages/43_North_Star_Coverage.py") call in app.py.
        assert PAGE.is_file(), f"missing pillar coverage page {PAGE}"

    def test_page_parses_as_python(self):
        # Source-guard #2 — the page is syntactically valid Python.
        # Streamlit scripts are imported by Streamlit at runtime; if
        # the module fails to parse, the dashboard crashes on first
        # navigation. Catches the typo / unterminated-string class of
        # regression that ruff format alone would miss.
        ast.parse(PAGE.read_text(encoding="utf-8"))

    def test_page_has_literal_page_header(self):
        # Mirrors the title-mining contract in
        # tests/test_dashboard_workflows.py: a literal
        # `page_header("<title>", ...)` is what other tests scan for.
        body = PAGE.read_text(encoding="utf-8")
        assert f'page_header(\n    "{NAV_TITLE}"' in body or f'page_header("{NAV_TITLE}"' in body, (
            f"page must call page_header with the exact title {NAV_TITLE!r}"
        )

    def test_page_uses_ensure_initialized(self):
        # Direct-URL robustness — same contract as Regulator Pulse /
        # Knowledge pages. A bookmark hit must populate session state.
        body = PAGE.read_text(encoding="utf-8")
        assert "ensure_initialized()" in body, "page must call ensure_initialized()"

    def test_page_is_read_only_no_buttons_or_engine_call(self):
        # PR-NS-1 contract — the page is a pure synthesis surface.
        # No buttons (would imply state mutation); no engine call
        # (would defeat the cached-run contract); no spec writes.
        body = PAGE.read_text(encoding="utf-8")
        forbidden = [
            ("st.button(", "page must not render mutation buttons"),
            ("st.form_submit_button(", "page must not render form-submit buttons"),
            ("run_spec(", "page must not call the engine — use cached session state"),
            ("load_spec(", "page must not reload the spec — use cached session state"),
            ("spec.dump_yaml(", "page must not write the spec"),
        ]
        for needle, msg in forbidden:
            assert needle not in body, msg

    def test_section_explainer_present_with_stable_id(self):
        # GenAI-on-every-page promise + stable audit/cache key.
        body = PAGE.read_text(encoding="utf-8")
        assert "section_explainer(" in body, "page missing section_explainer"
        assert 'section_id="north_star_coverage.page"' in body, "section_id drift"


class TestPillarCoverage:
    def test_all_eight_pillar_names_appear(self):
        # Source-guard #3 — the 8 pillar names from the
        # `project_aml_north_star` memory each appear in the page
        # source. Prevents accidentally shipping a page with 7 cards
        # (the bug class this guard exists to catch).
        body = PAGE.read_text(encoding="utf-8")
        missing = [p for p in PILLAR_NAMES if p not in body]
        assert not missing, (
            f"page is missing these pillar names from project_aml_north_star: {missing}"
        )

    def test_each_pillar_card_carries_a_link(self):
        # Source-guard #4 — at minimum 1 link per pillar (regex
        # check). Prevents accidentally shipping prose-only cards.
        # The link contract is `st.page_link("pages/<N>_...py", ...)`
        # — the canonical Streamlit nav-link idiom used elsewhere in
        # the dashboard.
        body = PAGE.read_text(encoding="utf-8")
        # Slice the body into per-pillar sections by splitting on the
        # CALL pattern `_render_pillar(\n    number=`. This
        # deliberately ignores the `def _render_pillar(...)` definition
        # so a page with N call sites yields N+1 slices (1 prelude
        # + N card segments). Splitting on bare `_render_pillar(`
        # would also catch the function definition and add a spurious
        # slice.
        call_marker = "_render_pillar(\n    number="
        slices = body.split(call_marker)
        # 1 prelude + 8 pillars = 9 slices.
        assert len(slices) == 9, (
            f"expected 8 `_render_pillar(number=...)` call sites "
            f"(one per pillar), got {len(slices) - 1}"
        )
        for idx, segment in enumerate(slices[1:], start=1):
            # Each card defines its links inline as a `links=[...]`
            # list of (title, "pages/...") tuples. Check the segment
            # up to the NEXT call site (already split out) for at
            # least one `"pages/<n>_..."` link literal.
            assert re.search(r'"pages/\d+_', segment), (
                f"pillar #{idx} ({PILLAR_NAMES[idx - 1]}) card has no "
                f"pages/<N>_...py link — prose-only cards are not allowed"
            )
        # Belt-and-suspenders: the page invokes a Streamlit link
        # renderer at least once. Either the bare `st.page_link(` or
        # the shared `link_to_page(` helper (which wraps `st.page_link`
        # and gracefully degrades when a target is persona-hidden) is
        # acceptable — the latter is preferred for cross-page navigation
        # on universal pages.
        link_call_re = re.compile(r"st\.page_link\(|link_to_page\(")
        assert link_call_re.search(body), (
            "page declares pages/ link literals but never calls a link "
            "renderer (`st.page_link` or `link_to_page`) — links won't render"
        )

    def test_status_classifications_named_explicitly(self):
        # The page's contract is that it MUST name COVERED and PARTIAL
        # classifications explicitly so a reviewer can scan the source
        # for honest coverage signals. GAP was a required status until
        # PR-EQ-3 (Round 27) closed the equivalence pillar — now that
        # every pillar is COVERED or PARTIAL, GAP is allowed but not
        # required. The original "honest about gaps" intent is
        # preserved: the page WILL re-name a GAP the moment a real one
        # surfaces (e.g. a new pillar is added to the north-star
        # memory). Until then, having zero GAPs is the desired state.
        body = PAGE.read_text(encoding="utf-8")
        for status in ("COVERED", "PARTIAL"):
            assert f'status="{status}"' in body, (
                f"page has no pillar classified {status!r} — the contract "
                f"requires the page name {status} pillars explicitly"
            )


class TestRegistration:
    def test_audience_has_north_star_pages_constant(self):
        # PR-NS-1 added a dedicated NORTH_STAR_PAGES constant rather
        # than folding into KNOWLEDGE_PAGES (different semantics: live-
        # run synthesis vs. static research brief).
        assert NORTH_STAR_PAGES == [NAV_TITLE], (
            f"NORTH_STAR_PAGES drift: expected {[NAV_TITLE]!r}, got {NORTH_STAR_PAGES!r}"
        )

    def test_app_registers_the_page(self):
        body = APP.read_text(encoding="utf-8")
        assert "pages/43_North_Star_Coverage.py" in body, (
            "app.py must register pages/43_North_Star_Coverage.py via st.Page(...) in ALL_PAGES"
        )
        assert f'title="{NAV_TITLE}"' in body, f"app.py must use the exact nav title {NAV_TITLE!r}"

    def test_app_routes_north_star_universally(self):
        # Universal-routing idiom — same pattern as KNOWLEDGE_PAGES.
        # Without this line every non-default persona's filter would
        # hide the page; the page must be visible to every persona.
        body = APP.read_text(encoding="utf-8")
        assert "relevant_titles.update(NORTH_STAR_PAGES)" in body, (
            "app.py must update relevant_titles with NORTH_STAR_PAGES "
            "inside the audience-filter block — otherwise the per-"
            "persona filter hides the page from non-default personas"
        )

    def test_north_star_not_in_audience_pages(self):
        # Keeping the page OUT of AUDIENCE_PAGES preserves the per-
        # persona operational cap. Same discipline as
        # KNOWLEDGE_PAGES (test_dashboard_knowledge.py pins this for
        # the Knowledge titles).
        for persona, pages in AUDIENCE_PAGES.items():
            assert NAV_TITLE not in pages, (
                f"{NAV_TITLE!r} leaked into AUDIENCE_PAGES[{persona!r}] — "
                f"would count against MAX_PAGES_PER_PERSONA="
                f"{MAX_PAGES_PER_PERSONA}; route universally instead "
                "(via NORTH_STAR_PAGES, same idiom as KNOWLEDGE_PAGES)"
            )

    def test_audience_module_has_no_streamlit_import(self):
        # audience.py is imported by unit tests (this test imports
        # NORTH_STAR_PAGES from it). It must not pull in streamlit at
        # module level — the unit-test CI only installs `.[dev]`.
        # Pinned by test_dashboard_knowledge.py for the wider module;
        # repeated here as a localised guard so a future edit that
        # adds `import streamlit` at the top of audience.py breaks
        # this test loudly.
        tree = ast.parse(AUDIENCE.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                names = [a.name for a in node.names]
                assert "streamlit" not in mod and "streamlit" not in names, (
                    "audience.py must not import streamlit at module level "
                    "(unit-test CI installs `.[dev]` only)"
                )
