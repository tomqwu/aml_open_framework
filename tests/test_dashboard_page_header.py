"""Source-guard: every dashboard page MUST call `page_header()`.

Sibling to ``test_dashboard_page_footer.py``. The footer guard caught
the bottom-clip bug systemically; this guard catches the inverse
silent-drift seen in issue #435 — Today shipped without a
``page_header()`` call and CI didn't notice because no test pinned the
top-of-page side.

``page_header()`` is not just a visual title — it also mounts the AI
assistant sidebar/FAB panels (PR-K / PR3) and the section-explainer
background-future poller. A page that skips the header silently loses
those affordances on its surface. The contract: every page in
``src/aml_framework/dashboard/pages/*.py`` imports and calls
``page_header`` at module scope, exactly like the footer.

If this test fails, the fix is two lines at the top of the page:

    from aml_framework.dashboard.components import page_header
    # ... ensure_initialized() etc ...
    page_header("Title", "Subtitle")
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "pages"

# Intentional exemptions — page filenames that legitimately do NOT call
# ``page_header()`` (e.g. pages that fully embed an external surface
# with their own title chrome). Add to this set only with a written
# reason. Bare "we forgot" entries are NOT acceptable.
EXEMPT_PAGES: set[str] = set()


def _page_files() -> list[Path]:
    return sorted(p for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_page_imports_page_header(page_file: Path) -> None:
    """Every page must import ``page_header`` from
    ``aml_framework.dashboard.components``."""
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports_page_header = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "aml_framework.dashboard.components":
                for alias in node.names:
                    if alias.name == "page_header":
                        imports_page_header = True
                        break
    assert imports_page_header, (
        f"{page_file.name} does not import `page_header` from "
        "`aml_framework.dashboard.components`. Add the import + call "
        "`page_header(title, subtitle)` near the top of the page (after "
        "`ensure_initialized()`) so the AI assistant panel + section-"
        "explainer poller mount on this surface."
    )


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_page_calls_page_header(page_file: Path) -> None:
    """Every page must contain a top-level ``page_header(...)`` call.

    Top-level here means: at module scope (not nested inside an
    ``if``/``for`` block), so the side effects (AI assistant + section-
    explainer poller) always mount.
    """
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_top_level_call = False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "page_header":
                found_top_level_call = True
                break
    assert found_top_level_call, (
        f"{page_file.name} does not call `page_header(...)` at module scope. "
        "Add `page_header(title, subtitle)` near the top of the page so the "
        "AI assistant panel + section-explainer poller mount unconditionally."
    )
