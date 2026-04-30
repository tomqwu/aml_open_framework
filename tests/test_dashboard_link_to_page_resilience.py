"""Regression guard for issue #69 (round 2) — link_to_page must not
crash a page render when the target is hidden by the persona filter.

PR-R fixed the Today cards by widening AUDIENCE_PAGES so card targets
always sit in the persona's nav set. But the same crash class showed
up immediately on Executive Dashboard's drill-down links (which point
at Alert Queue + Investigations from a page that's universal to every
persona). Closing that gap with audience-map widening alone would
force every persona to carry every page that any visible page links
to — which defeats the filter entirely.

Instead, `link_to_page` now catches both runtime failure modes and
renders a degraded caption hinting at the persona switch. This file
locks that contract in.
"""

from __future__ import annotations

from pathlib import Path

# Intentionally NO streamlit / aml_framework.dashboard.components imports
# at module level. `tests/test_dashboard_queue_state.py` runs an autouse
# fixture that asserts `streamlit not in sys.modules` (its production
# code must stay streamlit-free), and that assertion fires for ALL tests
# in the session if anything else pollutes sys.modules. So this file
# stays source-level only — it asserts the defensive code is present,
# not that it executes correctly. Live runtime behaviour is verified
# manually via the Playwright VP-mode smoke described in the PR.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"


# ---------------------------------------------------------------------------
# Source-level: the defensive try/except is in place
# ---------------------------------------------------------------------------


class TestLinkToPageHasDefensiveFallback:
    def test_link_to_page_wraps_st_page_link_in_try(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index("def link_to_page(")
        end = body.index("\ndef ", idx + 10)
        block = body[idx:end]
        assert "try:" in block, "link_to_page() must wrap st.page_link in try/except"
        assert "st.page_link(" in block
        assert "StreamlitPageNotFoundError" in block, (
            "Fallback must specifically reference StreamlitPageNotFoundError "
            "by name so future readers see what's being defended against"
        )

    def test_fallback_includes_persona_hint(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index("def link_to_page(")
        end = body.index("\ndef ", idx + 10)
        block = body[idx:end]
        # The degraded caption should tell the user WHY the link is
        # disabled (hidden by their persona filter), so they can fix it
        # by switching personas rather than thinking the app is broken.
        assert "persona" in block.lower(), (
            "Fallback caption must mention 'persona' so users understand "
            "the link is hidden by their audience selection, not broken"
        )

    def test_fallback_handles_keyerror_url_pathname(self):
        # AppTest harness + bare scripts raise KeyError('url_pathname')
        # for the same "no nav context" condition. Catch covers both.
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index("def link_to_page(")
        end = body.index("\ndef ", idx + 10)
        block = body[idx:end]
        assert "url_pathname" in block, (
            "Fallback must handle the KeyError('url_pathname') variant "
            "so bare-context callers (tests / scripts) don't crash either"
        )


# ---------------------------------------------------------------------------
# Source-level: also verify the catch is selective enough to surface
# unrelated bugs instead of swallowing them silently.
# ---------------------------------------------------------------------------


class TestLinkToPageDoesNotSwallowEverything:
    def test_unrelated_exceptions_still_raise(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index("def link_to_page(")
        end = body.index("\ndef ", idx + 10)
        block = body[idx:end]
        # The except block must `raise` for non-nav exceptions — defensive
        # catches that swallow everything are how mysterious failures hide.
        # Look for an explicit re-raise on the negative branch.
        assert "raise" in block, (
            "link_to_page() must re-raise unrelated exceptions, not "
            "swallow every error from st.page_link"
        )
        # And the conditional must be specific (not `except: pass`).
        assert "is_nav_failure" in block or "if not " in block
