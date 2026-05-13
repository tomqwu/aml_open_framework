"""Pin migrated pages keep calling `section_explainer`.

When sections are refactored over time, it's easy for a page author to
move code around and inadvertently drop the per-section Explain
popovers. This lint test pins the two reference-migration pages from
the rollout PR — once these guard-rails hold, future PRs that migrate
more pages can add themselves to `EXPECTED_CALL_COUNTS` below.
"""

from __future__ import annotations

from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "pages"

# (filename, minimum_call_count). Update when migrating more pages.
# Phase 1: 2 reference pages with multi-section explainers.
# Phase 2 (this PR): page-level explainer on every other page so the
# "GenAI on every page" promise holds even before per-section granularity
# ships in follow-up PRs.
EXPECTED_CALL_COUNTS = {
    "1_Executive_Dashboard.py": 3,
    "3_Alert_Queue.py": 3,
}

# Every dashboard page in pages/ must contain at least one section_explainer
# call. The lookup below pins which files are in scope so a future page
# addition is forced through this list (and therefore through the migration
# check). Mirrors PAGES_DIR.glob("*.py") minus __init__.py + the two
# multi-section pages above.
_EXPECTED_PAGE_LEVEL = {
    "0_Today.py",
    "0_Welcome.py",
    "10_Network_Explorer.py",
    "11_Live_Monitor.py",
    "12_Sanctions_Screening.py",
    "13_Model_Performance.py",
    "14_Data_Quality.py",
    "15_Run_History.py",
    "16_Rule_Tuning.py",
    "17_Customer_360.py",
    "18_Typology_Catalogue.py",
    "19_Comparative_Analytics.py",
    "20_Spec_Editor.py",
    "21_My_Queue.py",
    "22_Analyst_Review_Queue.py",
    "23_Tuning_Lab.py",
    "24_Investigations.py",
    "25_BOI_Workflow.py",
    "26_FinTech_Cockpit.py",
    "27_Regulator_Pulse.py",
    "28_Metrics_Taxonomy.py",
    "29_AI_Assistant.py",
    "2_Program_Maturity.py",
    "30_Data_Integration.py",
    "31_Information_Sharing.py",
    "32_Lineage_Explorer.py",
    "4_Case_Investigation.py",
    "5_Rule_Performance.py",
    "6_Risk_Assessment.py",
    "7_Audit_Evidence.py",
    "8_Framework_Alignment.py",
    "9_Transformation_Roadmap.py",
}


def test_migrated_pages_import_section_explainer():
    for fname in EXPECTED_CALL_COUNTS:
        src = (PAGES_DIR / fname).read_text(encoding="utf-8")
        assert "section_explainer" in src, (
            f"{fname} no longer imports `section_explainer`. "
            "If you removed it deliberately, also remove the entry "
            "from EXPECTED_CALL_COUNTS in this test."
        )


def test_migrated_pages_call_section_explainer_enough_times():
    """Each migrated page should still have at least the minimum number
    of section_explainer() call sites — proves the rollout wasn't
    silently undone by a later refactor."""
    for fname, min_count in EXPECTED_CALL_COUNTS.items():
        src = (PAGES_DIR / fname).read_text(encoding="utf-8")
        # Count `section_explainer(` invocations — naive but sufficient
        # (the import doesn't include the parens, so this excludes the
        # import line).
        call_count = src.count("section_explainer(")
        # Subtract 1 to discount the `import section_explainer` line
        # which doesn't carry parens but might be matched by a hypothetical
        # future formatting. Actually `section_explainer,` import line has
        # no `(`, so the count stays a pure count of call sites.
        assert call_count >= min_count, (
            f"{fname}: expected ≥{min_count} `section_explainer()` calls, "
            f"found {call_count}. Migration was silently undone — add "
            "popovers back, or update EXPECTED_CALL_COUNTS if you "
            "deliberately reduced coverage."
        )


def test_each_call_has_stable_section_id():
    """A stable `section_id` is the cache key + audit-log identifier.
    Migrating pages without an explicit slug breaks both — pin that
    every call site uses a `section_id="..."` kwarg with a literal."""
    import re

    pattern = re.compile(r'section_explainer\([^)]*section_id\s*=\s*"[^"]+"', re.DOTALL)
    for fname in EXPECTED_CALL_COUNTS:
        src = (PAGES_DIR / fname).read_text(encoding="utf-8")
        call_count = src.count("section_explainer(")
        literal_id_count = len(pattern.findall(src))
        assert literal_id_count == call_count, (
            f"{fname}: every `section_explainer(...)` call must include "
            f'a string-literal `section_id="..."` kwarg. Found '
            f"{literal_id_count} with literals out of {call_count} calls."
        )


def test_every_page_has_at_least_one_explainer():
    """The user's standing requirement is 'GenAI on every page'. Pages
    listed in `_EXPECTED_PAGE_LEVEL` must each contain ≥1 `section_explainer(`
    call; pages in `EXPECTED_CALL_COUNTS` have their own (higher) threshold.

    If a new page is added to `pages/`, it must either be added to one of
    these two lookups, or the dashboard's per-page coverage promise is
    silently broken. Discover via `PAGES_DIR.glob`."""
    pages_actual = {p.name for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py"}
    pages_pinned = set(EXPECTED_CALL_COUNTS) | _EXPECTED_PAGE_LEVEL
    missing = pages_actual - pages_pinned
    assert not missing, (
        "These pages exist on disk but aren't pinned by either "
        "EXPECTED_CALL_COUNTS or _EXPECTED_PAGE_LEVEL: "
        f"{sorted(missing)}. Add a section_explainer() call to each + "
        "add the filename to _EXPECTED_PAGE_LEVEL (or to "
        "EXPECTED_CALL_COUNTS for multi-section pages)."
    )

    for fname in _EXPECTED_PAGE_LEVEL:
        src = (PAGES_DIR / fname).read_text(encoding="utf-8")
        call_count = src.count("section_explainer(")
        assert call_count >= 1, (
            f"{fname}: page-level GenAI coverage requires ≥1 "
            f"`section_explainer()` call. Found {call_count}."
        )
