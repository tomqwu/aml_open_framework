"""Regression guard for the sidebar-cannot-be-reopened bug (issue #69).

A previous CSS rule hid `[data-testid="stToolbar"]` wholesale to remove
Streamlit Cloud's Deploy button + 3-dot menu. That selector also wraps
the sidebar collapse/expand chevron in some Streamlit releases, so once
a user collapsed the sidebar they had no way to bring it back.

These source-level checks lock in the fix:
- the wholesale toolbar suppression is gone
- the deploy/menu/status widgets are still hidden by narrow selectors
- the sidebar collapse/expand controls are explicitly forced visible
"""

from __future__ import annotations

from pathlib import Path

COMPONENTS_FILE = (
    Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "components.py"
)


def _css() -> str:
    return COMPONENTS_FILE.read_text(encoding="utf-8")


class TestNoWholesaleToolbarSuppression:
    def test_stToolbar_is_not_display_none(self):
        body = _css()
        # The previous bug: `[data-testid="stToolbar"] { display: none }`
        # nuked the sidebar-expand control along with the deploy button.
        # The selector must not appear in any display:none rule.
        assert '[data-testid="stToolbar"]' not in body, (
            "stToolbar must NOT be hidden wholesale — it contains the "
            "sidebar collapse/expand control. Hide stDeployButton + "
            "stMainMenu + stStatusWidget individually instead."
        )


class TestNarrowChromeSuppression:
    def test_deploy_button_still_hidden(self):
        body = _css()
        assert ".stDeployButton" in body or '[data-testid="stDeployButton"]' in body

    def test_main_menu_still_hidden(self):
        body = _css()
        # The 3-dot menu in the top-right uses stMainMenu in modern Streamlit.
        assert '[data-testid="stMainMenu"]' in body, (
            "Deploy/menu cleanup must explicitly target stMainMenu now that "
            "stToolbar is no longer suppressed wholesale"
        )

    def test_status_widget_still_hidden(self):
        body = _css()
        assert '[data-testid="stStatusWidget"]' in body


class TestSidebarCollapseControlVisible:
    def test_collapsed_control_explicit_safeguard(self):
        body = _css()
        # The floating "open sidebar" arrow that appears when the user
        # collapses the sidebar. Without an explicit safeguard, a future
        # Streamlit DOM change could nest it under a parent we accidentally
        # suppress and re-introduce the bug.
        assert '[data-testid="stSidebarCollapsedControl"]' in body
        # Both the historical and current testids should be covered.
        assert '[data-testid="collapsedControl"]' in body

    def test_collapse_button_explicit_safeguard(self):
        body = _css()
        # The chevron INSIDE the sidebar header (used to collapse) —
        # belt-and-braces so it can never be hidden by future regressions.
        assert '[data-testid="stSidebarCollapseButton"]' in body

    def test_expand_button_explicit_safeguard(self):
        body = _css()
        # Modern Streamlit (≥1.50) renders the floating "open sidebar"
        # control as [data-testid="stExpandSidebarButton"] instead of the
        # older stSidebarCollapsedControl. Both must be in the safeguard.
        assert '[data-testid="stExpandSidebarButton"]' in body, (
            "Modern Streamlit's expand-sidebar button (stExpandSidebarButton) "
            "must be in the visibility safeguard — verified live on "
            "Streamlit 1.56."
        )

    def test_safeguards_force_visible(self):
        body = _css()
        # The safeguard block must declare display + visibility + opacity
        # all in the "visible" state so a more-specific later rule cannot
        # silently re-hide the controls.
        # Locate the block by anchoring on the collapsed-control selector.
        idx = body.index('[data-testid="stSidebarCollapsedControl"]')
        block = body[idx : idx + 400]
        assert "display: flex !important" in block
        assert "visibility: visible !important" in block
        assert "opacity: 1 !important" in block
