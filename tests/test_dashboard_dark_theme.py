"""Unit guards for the OS-following dark theme.

A live screenshot showed the dashboard illegible in OS dark mode:
the app was hard-locked to its light "DNA" palette (config.toml
hard-pinned a light bg/text, `color-scheme: light`, no
`@media (prefers-color-scheme: dark)` block), so dark-navy ink
rendered on a dark canvas. PR-1 adds a real dark theme: every
`--dna-*` var is redefined under a dark media query and the
previously-hardcoded inline colours (KPI value/label, metric
label, hero tint background) were refactored to read the vars so
they flip too.

These source-level checks run on the minimal unit-test CI image
(no Streamlit / browser) and are a fast guard against the dark
theme being accidentally dropped or re-hardcoded. The real
rendered-contrast assertion lives in the Playwright dark-mode e2e.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
CONFIG_FILE = PROJECT_ROOT / ".streamlit" / "config.toml"


class TestDarkMediaQueryPresent:
    def test_prefers_color_scheme_dark_block_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "@media (prefers-color-scheme: dark)" in body, (
            "Dark theme media query missing — the app would be illegible in OS dark mode again"
        )

    def test_color_scheme_not_hard_locked_to_light(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Must allow both schemes so the UA renders scrollbars/controls
        # correctly in dark; the old hard `color-scheme: light;` lock
        # is the regression we're guarding against.
        assert "color-scheme: light dark;" in body
        assert "color-scheme: light;" not in body

    def test_dark_block_redefines_core_dna_vars(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(
            r"@media \(prefers-color-scheme: dark\)\s*\{(.+?)\n\}",
            body,
            re.DOTALL,
        )
        assert m, "Could not isolate the dark media-query block"
        block = m.group(1)
        # The role-bearing vars must all be redefined for dark, or
        # parts of the UI keep their light values and clash.
        for var in (
            "--dna-bg:",
            "--dna-bg-card:",
            "--dna-ink:",
            "--dna-ink-dim:",
            "--dna-accent:",
            "--dna-rule:",
            "--dna-sidebar-bg:",
        ):
            assert var in block, f"dark block missing {var} redefinition"


class TestNoReintroducedHardcodedLightColors:
    """The hero KPI tiles + metric cards must colour via `--dna-*`
    vars, never the old hardcoded light-mode hex, or they render as
    light slabs on the dark canvas (the exact reported bug)."""

    def test_hero_kpi_inline_colors_use_vars(self):
        """Scope to the `headline_hero` function — the reported bug
        locus (the OPEN ALERTS / RAG / OPEN CASES tiles). A file-wide
        hex ban would wrongly flag legitimately-dark elements like
        `.terminal-block` / the tour panel, which are dark in BOTH
        schemes by design."""
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        start = body.index("def headline_hero(")
        end = body.index("\ndef ", start + 1)
        hero = body[start:end]
        for bad in ("color:#0f172a", "color: #0f172a", "color:#64748b", "color: #64748b"):
            assert bad not in hero, (
                f"headline_hero reintroduced hardcoded {bad!r} — KPI tiles won't flip in dark mode"
            )

    def test_hero_tint_gradient_ends_on_theme_surface(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The hero RAG tint must blend into the themed card surface,
        # not a hardcoded `white` (which stays a light slab on dark).
        assert "0%, white 100%)" not in body
        assert "var(--dna-bg-card) 100%)" in body

    def test_metric_card_value_label_use_vars(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Spot-check the .metric-card .value / .label rules.
        assert ".metric-card .value {" in body
        m = re.search(r"\.metric-card \.value \{(.+?)\}", body, re.DOTALL)
        assert m and "var(--dna-ink)" in m.group(1)


class TestConfigTomlNotHardPinningLightCanvas:
    """A static config.toml can't be scheme-aware; hard-pinning a
    light backgroundColor/textColor was what made dark mode illegible.
    Guard that those pins stay out."""

    def test_no_hardpinned_background_or_text_color(self):
        cfg = CONFIG_FILE.read_text(encoding="utf-8")
        # Match actual TOML key ASSIGNMENTS, not the words appearing in
        # the explanatory comment.
        assign = [
            ln.strip() for ln in cfg.splitlines() if ln.strip() and not ln.strip().startswith("#")
        ]
        keys = {ln.split("=", 1)[0].strip() for ln in assign if "=" in ln}
        assert "backgroundColor" not in keys, (
            "config.toml re-pinned backgroundColor — a static value can't "
            "be scheme-aware and re-breaks OS dark mode"
        )
        assert "textColor" not in keys
        assert "secondaryBackgroundColor" not in keys
        # primaryColor (accent) + font are scheme-neutral and may stay.
        assert 'primaryColor = "#a44b30"' in cfg
