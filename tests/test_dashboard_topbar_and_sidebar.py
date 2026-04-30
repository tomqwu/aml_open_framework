"""Source-level guards for PR-P — global topbar + ivory sidebar + hero.

The dashboard previously kept the brand wordmark inside the sidebar
(invisible the moment a user collapsed the panel) and rendered the
sidebar as a dark slab against the cream body. PR-P moves the wordmark
to a fixed top-left bar that mirrors the static landing site
(``docs/pitch/landing/index.html``) and recolours the sidebar to ivory.

These checks lock in the new contract without needing a Streamlit
runtime — they assert the generated CSS + HTML strings directly.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
APP_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
TODAY_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "0_Today.py"


class TestGlobalTopbar:
    def test_topbar_css_class_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert ".dna-topbar" in body, "Global topbar CSS class missing"

    def test_topbar_is_position_fixed(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index(".dna-topbar")
        block = body[idx : idx + 800]
        assert "position: fixed" in block
        assert "top: 0" in block

    def test_topbar_uses_landing_cream_background(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The exact rgba lifted from docs/pitch/landing/index.html
        # (`--bg-nav: rgba(247, 244, 236, 0.92)`). Locking the value
        # prevents drift away from the marketing-site palette.
        assert "rgba(247, 244, 236, 0.92)" in body

    def test_topbar_height_variable_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "--dna-topbar-h:" in body, (
            "Topbar height must be tokenised so the page-padding rule and "
            "the topbar element stay in sync"
        )

    def test_app_renders_topbar_html(self):
        body = APP_FILE.read_text(encoding="utf-8")
        assert 'class="dna-topbar"' in body
        assert "AML Open Framework" in body
        assert "dna-topbar-dot" in body
        assert "dna-topbar-name" in body

    def test_app_view_padded_below_topbar(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Without this rule the topbar overlaps the first row of content.
        assert "padding-top: var(--dna-topbar-h)" in body

    def test_sidebar_pushed_below_topbar(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The sidebar is position:fixed top:0 by default — must be bumped
        # down so the topbar sits unobstructed above it.
        assert "top: var(--dna-topbar-h) !important" in body


class TestSidebarRecoloured:
    def test_sidebar_bg_is_ivory_not_dark(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The PR-N dark slab #1c1f26 must be gone from the sidebar token.
        # Find the --dna-sidebar-bg declaration and assert its value.
        assert "--dna-sidebar-bg: #fdfbf5" in body, (
            "Sidebar background must match the landing card panel "
            "(--bg-card #fdfbf5), not the deck-tech dark slab"
        )

    def test_sidebar_ink_is_dark_not_light(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Text on ivory must be the dark navy ink, not slate-100.
        assert "--dna-sidebar-ink: #1c1f26" in body

    def test_no_dark_sidebar_slab_color_in_token(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Defensive: the original dark hex must not be the active value
        # for the sidebar token. (It still appears as --dna-ink, which
        # is correct for ink-on-cream — search is therefore scoped.)
        idx = body.index("--dna-sidebar-bg:")
        line_end = body.index("\n", idx)
        decl = body[idx:line_end]
        assert "#1c1f26" not in decl, (
            "Sidebar token still set to the old dark slab — recolour skipped"
        )


class TestSidebarWordmarkRemoved:
    def test_app_no_longer_renders_dna_brand_block(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # The `dna-brand` block was the in-sidebar wordmark. With the
        # global topbar carrying the brand, keeping the sidebar copy is
        # redundant chrome. Asserting absence guards against a future
        # revert.
        assert 'class="dna-brand"' not in body, (
            "Sidebar wordmark must be removed once the global topbar ships "
            "— two wordmarks side-by-side reads as a duplicated logo"
        )


class TestTodayHero:
    def test_today_renders_hero_block(self):
        body = TODAY_FILE.read_text(encoding="utf-8")
        assert 'class="dna-hero"' in body
        assert 'class="dna-hero-title"' in body
        assert 'class="dna-hero-lede"' in body

    def test_hero_css_uses_serif_display(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index(".dna-hero-title")
        block = body[idx : idx + 600]
        assert "var(--dna-display)" in block, (
            "Hero title must use the Source Serif display stack — "
            "matches the landing site's hero typography"
        )

    def test_hero_title_uses_accent_for_italic(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        idx = body.index(".dna-hero-title em")
        block = body[idx : idx + 200]
        assert "var(--dna-accent)" in block
