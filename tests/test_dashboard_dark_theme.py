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

import pytest

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
            "--dna-topbar-bg:",
            "--dna-card-border:",
        ):
            assert var in block, f"dark block missing {var} redefinition"

    def test_cards_use_dedicated_border_var(self):
        """KPI/metric cards must border via `--dna-card-border` (a
        solid dark-mode mid-grey clearing WCAG 1.4.11's 3:1), NOT the
        translucent general `--dna-rule` hairline which can't reach
        3:1 on the near-black canvas."""
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        for rule_start in ('div[data-testid="stMetric"] {', ".metric-card {"):
            i = body.index(rule_start)
            rule = body[i : body.index("}", i)]
            assert "var(--dna-card-border)" in rule, (
                f"{rule_start} must border via --dna-card-border"
            )


class TestVisibleChromeUsesVars:
    """Codex review caught topbar / headers / native metric value
    still hardcoded light → invisible in dark. Pin them on vars."""

    def test_topbar_background_uses_var(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"\.dna-topbar \{(.+?)\}", body, re.DOTALL)
        assert m, ".dna-topbar rule not found"
        assert "var(--dna-topbar-bg)" in m.group(1), (
            "topbar bg hardcoded — stays a cream slab in dark mode"
        )
        assert "rgba(247, 244, 236, 0.92)" not in m.group(1)

    def test_headers_and_metric_value_use_vars(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        for sel in ("h2 {", "h3 {"):
            i = body.index(sel)
            rule = body[i : body.index("}", i)]
            assert "var(--dna-ink" in rule, f"{sel} colour hardcoded"
        i = body.index('[data-testid="stMetricValue"] {')
        rule = body[i : body.index("}", i)]
        assert "var(--dna-ink)" in rule, "stMetricValue colour hardcoded"
        # The specific failing hexes Codex flagged must be gone from
        # these var-driven rules.
        assert "color: #1e293b !important" not in body
        assert "color: #334155 !important" not in body


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
        # This guards the REPO's `.streamlit/config.toml`. The Docker
        # image deliberately does not copy `.streamlit/` (the deployed
        # app's theme is the injected CSS, not config.toml), and the
        # docker-build CI job runs the suite inside that image — so the
        # file is legitimately absent there. Skip rather than
        # FileNotFoundError; the guard is meaningful only where the
        # source-tree config exists.
        if not CONFIG_FILE.exists():
            pytest.skip(
                ".streamlit/config.toml absent (running inside the "
                "Docker image, which doesn't ship it) — repo-config "
                "guard not applicable here"
            )
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


class TestPr3SecondaryChromeFollowsTheme:
    """PR-3 component sweep: the secondary chrome that PR-1 missed —
    deep-link colour, the "(no prior runs)" / AI-assistant /
    citation-count muted labels — was hardcoded to cream-tuned light
    hexes (#2563eb / #94a3b8 / #64748b) that don't flip in OS dark
    mode. They now route through the dark-aware `--dna-*` tokens.

    These are small *functional* labels, so they must use
    `--dna-ink-dim` (4.95:1 on the cream card / 5.81:1 on the dark
    card — clears WCAG 4.5:1 text on BOTH), NOT `--dna-ink-faint`:
    that token is an *intentionally* low-contrast de-emphasis colour
    (light #9aa3ad is only 2.33:1 on cream — fails even the 3:1
    non-text bar). Routing readable labels onto faint just moves the
    regression from dark to light — caught in Codex PR-3 review.

    The SVG sparkline stroke can't take `var()` (presentation attr),
    so it uses the fixed dual-contrast-safe #6b7280 the theme-neutral
    charts use. Semantic confidence/RAG colours are a DELIBERATELY
    separate follow-up (convention vs contrast) and not asserted here.
    """

    def test_deep_link_uses_accent_token_not_fixed_blue(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "color:#2563eb" not in body, (
            "tile deep-link still hardcodes #2563eb — invisible-ish on the dark card"
        )
        assert "color:var(--dna-accent);text-decoration:none" in body

    def test_muted_labels_use_ink_dim_not_faint(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The three converted functional-label fragments must carry
        # the readable dark-aware DIM token, not the old fixed
        # #94a3b8 / #64748b, and NOT the de-emphasis FAINT token
        # (which fails 3:1 on the cream card — Codex PR-3).
        assert "var(--dna-ink-dim);font-size:0.78rem" in body, "(no prior runs) not tokenised"
        assert ("text-transform:uppercase; color:var(--dna-ink-dim);") in body, (
            "AI-assistant label not tokenised"
        )
        assert 'color:var(--dna-ink-dim);">{citation_count}' in body, (
            "citation-count label not tokenised"
        )
        # The retired light-only hexes must be gone from these
        # neutral-chrome spots (semantic 'low'=#94a3b8 confidence
        # fallback is a separate deferred concern and may remain).
        assert "color:#94a3b8;font-size:0.78rem" not in body
        assert "text-transform:uppercase; color:#94a3b8;" not in body
        assert 'color:#64748b;">{citation_count}' not in body
        # Regression guard: these specific functional labels must not
        # be routed onto the faint de-emphasis token.
        assert "var(--dna-ink-faint);font-size:0.78rem" not in body
        assert "text-transform:uppercase; color:var(--dna-ink-faint);" not in body
        assert 'color:var(--dna-ink-faint);">{citation_count}' not in body

    def test_sparkline_neutral_is_dual_contrast_safe(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # SVG stroke can't take var() as a presentation attr, so it
        # uses the fixed dual-safe neutral the theme-neutral charts
        # use (4.40:1 on cream / 3.07:1 on the dark card). The old
        # #64748b was ~3.12:1 on dark — clears non-text 3:1 but is
        # marginal and not the single source-of-truth neutral.
        assert '"neutral": "#6b7280"' in body
        assert '.get(delta_dir, "#6b7280")' in body
        assert '"neutral": "#64748b"' not in body
