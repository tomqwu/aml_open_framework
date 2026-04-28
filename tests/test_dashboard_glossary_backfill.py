"""Tests verifying glossary_term/legend is wired into leader pages.

PR #108 added the helper. This PR (the glossary backfill) actually
calls it from the four leader-facing pages (Welcome, Audit & Evidence,
Investigations, Tuning Lab). Without these tests, a future contributor
can silently rip the legend out and a leader once again sees bare
acronyms with no definition.

Each test reads the page source as text — the helper outputs HTML that
Streamlit renders via `unsafe_allow_html=True`, so a unit-style render
test would require booting Streamlit. Source-text inspection is enough
to catch the regression we care about.
"""

from __future__ import annotations

from pathlib import Path

PAGES = Path(__file__).resolve().parent.parent / "src" / "aml_framework" / "dashboard" / "pages"


# Pages that should call glossary_legend(...) and the must-have terms
# we expect to appear inside that call. The tests are deliberately
# lenient about positioning (legend can be anywhere on the page) but
# strict about presence.
EXPECTED_LEGEND_TERMS: dict[str, set[str]] = {
    "0_Welcome.py": {"1LoD", "2LoD", "STR", "KYC", "SLA"},
    "7_Audit_Evidence.py": {"STR", "SAR", "FINTRAC", "OSFI", "FCA", "AMLA", "FinCEN", "MRM"},
    "24_Investigations.py": {"SLA", "STR", "SAR", "MLRO"},
    "23_Tuning_Lab.py": {"MRM", "2LoD"},
}


def _page_text(filename: str) -> str:
    path = PAGES / filename
    assert path.exists(), f"page {filename} missing on disk"
    return path.read_text(encoding="utf-8")


def test_each_leader_page_imports_glossary_helper() -> None:
    for filename in EXPECTED_LEGEND_TERMS:
        body = _page_text(filename)
        assert "glossary_legend" in body, (
            f"{filename}: missing import or call to glossary_legend — "
            "leaders will see bare acronyms"
        )


def test_each_leader_page_calls_glossary_legend_with_expected_terms() -> None:
    for filename, expected_terms in EXPECTED_LEGEND_TERMS.items():
        body = _page_text(filename)
        # Find the glossary_legend(...) call and pull out the literal list
        # contents. Tolerates both single-line and multiline formatting.
        import re

        matches = re.findall(r"glossary_legend\(\s*\[([^\]]+)\]", body)
        assert matches, f"{filename}: no glossary_legend([...]) call found"
        listed = " ".join(matches)
        for term in expected_terms:
            quoted = f'"{term}"'
            single = f"'{term}'"
            assert quoted in listed or single in listed, (
                f"{filename}: glossary_legend missing required term {term!r}. "
                f"Found terms: {listed!r}"
            )


def test_legend_is_rendered_with_unsafe_allow_html() -> None:
    """The legend output is HTML; if a contributor forgets the
    `unsafe_allow_html=True` flag on the surrounding `st.markdown(...)`,
    Streamlit will escape the tags and the leader sees raw <span> markup.
    Catch that mistake at the source level."""
    for filename in EXPECTED_LEGEND_TERMS:
        body = _page_text(filename)
        # Find the markdown call that wraps glossary_legend(...) — it
        # should carry unsafe_allow_html=True.
        import re

        # crude but effective: ensure that within ~120 chars after a
        # glossary_legend call there's an unsafe_allow_html=True flag.
        for m in re.finditer(r"glossary_legend\(", body):
            window = body[max(0, m.start() - 80) : m.end() + 200]
            assert "unsafe_allow_html=True" in window, (
                f"{filename}: glossary_legend call near char {m.start()} "
                "is not wrapped in st.markdown(..., unsafe_allow_html=True)"
            )
