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


def test_ensure_initialized_reapplies_theme_on_direct_page_hit(monkeypatch):
    """A direct-URL hit on a sub-page only executes the page script —
    `app.py` doesn't run, so its `apply_theme()` call doesn't run.
    Without re-applying the custom CSS on the page, body background
    falls back to the browser UA — black if `prefers-color-scheme:
    dark`. Pin that `ensure_initialized()` re-injects the theme."""
    import sys
    from unittest import mock

    # Fake `streamlit` so the imports inside state.py / components.py
    # succeed without a real Streamlit context.
    fake_st = mock.MagicMock()
    fake_st.session_state = {"spec": object(), "active_cache_key": "x:42"}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    # Rebind the module-global `st` reference inside state.py + components.
    import aml_framework.dashboard.components as components_mod
    import aml_framework.dashboard.state as state_mod

    monkeypatch.setattr(state_mod, "st", fake_st)
    monkeypatch.setattr(components_mod, "st", fake_st)

    # Patch apply_theme so we can observe whether ensure_initialized
    # calls it. Use a real attribute (function-attr trick) so the import
    # inside ensure_initialized resolves to our mock.
    apply_theme_calls: list[None] = []

    def fake_apply_theme():
        apply_theme_calls.append(None)

    monkeypatch.setattr(components_mod, "apply_theme", fake_apply_theme)

    state_mod.ensure_initialized()
    assert apply_theme_calls, (
        "ensure_initialized() must call apply_theme() — otherwise a "
        "direct sub-page hit shows browser-default styling on the body "
        "(black background in dark mode)."
    )
