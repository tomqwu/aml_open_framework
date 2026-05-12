"""Lint test — every dashboard page must call ensure_initialized().

The hotfix on 2026-05-12: Azure Container Apps revision rolled, the
user's bookmarked URL `/Today` reloaded against a fresh pod, the entry
script `app.py` never ran on that script execution, and the page died
on the first `st.session_state.spec` access.

Streamlit's multipage layout runs `app.py` *only* when the user lands
at the root URL. A direct hit to `/Today` (or any sub-page) only runs
the page script. Without a guard at the top of every page, sub-page
URLs are fragile — bookmarks, deep links, and pod restarts all trigger
the AttributeError.

This test pins: every `pages/*.py` file must call `ensure_initialized()`
(or import it). It cannot be a true e2e because the e2e fixture always
starts at `/` (running app.py), which masks the regression.
"""

from __future__ import annotations

from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "pages"


def test_every_page_calls_ensure_initialized():
    """Every `pages/*.py` must call `ensure_initialized()` at module level."""
    failures: list[str] = []
    for page_file in sorted(PAGES_DIR.glob("*.py")):
        if page_file.name == "__init__.py":
            continue
        src = page_file.read_text(encoding="utf-8")
        if "ensure_initialized()" not in src:
            failures.append(page_file.name)
    assert not failures, (
        "These dashboard pages do not call ensure_initialized() and will "
        "crash on direct-URL hits (bookmark / pod restart / deep link): "
        f"{failures}. Add at the top of each:\n\n"
        "    from aml_framework.dashboard.state import ensure_initialized\n\n"
        "    ensure_initialized()\n"
    )
