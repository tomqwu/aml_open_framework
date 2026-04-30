"""Pin `docs/dashboard-tour.md` to the current state of `pages/`.

This is the prevention pattern Issue #68 wished it had: when a new
dashboard page lands without a corresponding tour entry, this test
fails in CI rather than letting drift accumulate for 30 days until
a manual sweep ticket fires.

Mirrors the read-as-text style of `tests/test_docs_links.py`.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"
TOUR = PROJECT_ROOT / "docs" / "dashboard-tour.md"

# Pages that intentionally don't appear as standalone tour entries.
# `0_Welcome.py` and `0_Today.py` are navigation surfaces (welcome page
# + today checklist) — they're documented elsewhere, not in the
# per-page tour. Add a page to this set with a one-line justification
# rather than leaving the tour silently incomplete.
TOUR_EXEMPT = {
    "0_Welcome.py",
    "0_Today.py",
}

# Some page files use a slug that doesn't match the tour heading
# verbatim (the tour uses prose punctuation: ampersands, parentheses,
# Round-N qualifiers). Map filename → exact tour heading text.
TOUR_HEADING_OVERRIDES = {
    "7_Audit_Evidence.py": "Audit & Evidence",
    "20_Spec_Editor.py": "Spec Editor & Rule Builder",
    "24_Investigations.py": "Investigations (Round-6)",
    "21_My_Queue.py": "My Queue (Analyst Dashboard)",
    "2_Program_Maturity.py": "Program Maturity Assessment",
}


def _page_files() -> list[Path]:
    """Every numbered page file in the pages/ directory."""
    return sorted(p for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py")


def _page_title_from_filename(filename: str) -> str:
    """`25_BOI_Workflow.py` → `BOI Workflow`. Honors TOUR_HEADING_OVERRIDES."""
    if filename in TOUR_HEADING_OVERRIDES:
        return TOUR_HEADING_OVERRIDES[filename]
    stem = filename.removesuffix(".py")
    # Drop the leading number + underscore.
    if "_" in stem:
        _num, _, name = stem.partition("_")
        return name.replace("_", " ")
    return stem


class TestTourMentionsEveryPage:
    def test_every_page_has_a_tour_entry(self):
        body = TOUR.read_text(encoding="utf-8")
        missing: list[str] = []
        for page_file in _page_files():
            if page_file.name in TOUR_EXEMPT:
                continue
            title = _page_title_from_filename(page_file.name)
            # The tour uses ### headings for each page; the title may
            # be exactly the file-derived title or a close variant
            # (e.g., "Spec Editor & Rule Builder" when the file is
            # `20_Spec_Editor.py`). Accept either:
            #   - exact `### Title`
            #   - `### Title` followed by additional words
            heading_match = (
                f"### {title}\n" in body or f"### {title} " in body or f"### {title}\r\n" in body
            )
            if not heading_match:
                missing.append(f"{page_file.name} → expected tour heading containing '{title}'")
        assert not missing, (
            "Pages missing from `docs/dashboard-tour.md`:\n  "
            + "\n  ".join(missing)
            + "\n\nAdd a section under the appropriate category, or add the file "
            "to TOUR_EXEMPT in this test with a one-line justification."
        )

    def test_page_count_in_header_matches_described(self):
        """The tour's header line ('N purpose-built pages') must match
        the count of pages this tour actually describes — i.e. all
        page files minus TOUR_EXEMPT. (Welcome / Today are navigation
        surfaces documented separately.)"""
        body = TOUR.read_text(encoding="utf-8")
        described_count = len(_page_files()) - len(TOUR_EXEMPT)
        expected_phrase = f"**{described_count} purpose-built pages**"
        assert expected_phrase in body, (
            f"Tour header must claim {described_count} pages (file count "
            f"{len(_page_files())} minus {len(TOUR_EXEMPT)} TOUR_EXEMPT entries). "
            f"Looking for: {expected_phrase!r}"
        )

    def test_audience_filtering_count_matches_persona_count(self):
        """The audience-filtering section counts personas. If audience.py
        adds a persona, the count needs to bump."""
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        body = TOUR.read_text(encoding="utf-8")
        n_personas = len(AUDIENCE_PAGES)
        # Tour says e.g. "11 distinct personas" — accept some tolerance
        # since the phrasing may use "10" + an inline FinTech mention,
        # but a number must appear and equal the personas dict size.
        expected = f"{n_personas} distinct personas"
        assert expected in body, (
            f"Tour audience-filtering section must claim {n_personas} distinct "
            f"personas to match `AUDIENCE_PAGES` in audience.py. Looking for: "
            f"{expected!r}"
        )
