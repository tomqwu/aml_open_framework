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
EXPECTED_CALL_COUNTS = {
    "1_Executive_Dashboard.py": 3,
    "3_Alert_Queue.py": 3,
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
