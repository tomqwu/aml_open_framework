"""Phase E — per-page polish + design-system consistency.

Source-level checks that:
  - Every page renders a `page_header(...)` at module top — the
    audience-filtering test catches missing entries in the audience
    map; this catches missing headers (which would still show the page
    but with no title).
  - Pages flagged by the workflow audit as crash-prone on degenerate
    specs (zero rules / zero txns) now have empty-state guards.
  - Pages don't reach into the Phase A `SLA_BAND_COLORS`/
    `SEVERITY_COLORS` constants directly; they call the
    `severity_color` / `sla_band_color` resolvers so future palette
    changes flow through one place.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"

# Pages that were flagged by the Phase E audit as missing empty-state
# defenses. They previously crashed on degenerate specs (zero rules,
# zero txns); the guards convert the crash into an `empty_state` call.
EMPTY_STATE_GUARDED_PAGES = {
    "5_Rule_Performance.py": "spec.rules",
    "10_Network_Explorer.py": "df_txns",
    "11_Live_Monitor.py": "df_txns",
}


class TestEveryPageHasHeader:
    def test_every_page_calls_page_header(self):
        missing: list[str] = []
        for f in sorted(PAGES_DIR.glob("*.py")):
            if f.name == "__init__.py":
                continue
            body = f.read_text(encoding="utf-8")
            if "page_header(" not in body:
                missing.append(f.name)
        assert not missing, "Pages missing `page_header(...)`:\n  " + "\n  ".join(missing)


class TestEmptyStateDefenses:
    def test_flagged_pages_import_empty_state(self):
        for page_name in EMPTY_STATE_GUARDED_PAGES:
            body = (PAGES_DIR / page_name).read_text(encoding="utf-8")
            assert "empty_state" in body, (
                f"{page_name} is in EMPTY_STATE_GUARDED_PAGES but doesn't import empty_state"
            )

    def test_rule_performance_guards_zero_rules(self):
        body = (PAGES_DIR / "5_Rule_Performance.py").read_text(encoding="utf-8")
        # The guard must be a top-level check, not buried inside a
        # function — otherwise it doesn't fire on page load.
        assert "if not spec.rules:" in body
        assert "stop=True" in body

    def test_network_explorer_guards_empty_txns(self):
        body = (PAGES_DIR / "10_Network_Explorer.py").read_text(encoding="utf-8")
        assert "df_txns" in body
        # Look for the empty-frame guard — must come BEFORE the agraph
        # build so we don't waste compute on data we'll throw away.
        guard_idx = body.find("df_txns is None or df_txns.empty")
        agraph_idx = body.find("agraph(nodes=nodes")
        assert guard_idx > 0
        assert agraph_idx > 0
        assert guard_idx < agraph_idx, "Empty-frame guard must run before the agraph render"

    def test_live_monitor_guards_empty_txns(self):
        body = (PAGES_DIR / "11_Live_Monitor.py").read_text(encoding="utf-8")
        assert "df_txns is None or df_txns.empty" in body
        # Guard must precede the live-replay loop (sort_values('booked_at')).
        guard_idx = body.find("df_txns is None or df_txns.empty")
        loop_idx = body.find("df_txns.sort_values")
        assert guard_idx > 0
        assert loop_idx > 0
        assert guard_idx < loop_idx


class TestColorSystemConsistency:
    """Pages should NOT reach into the Phase A SEVERITY_COLORS /
    SLA_BAND_COLORS constants for direct lookup. They should call the
    `severity_color` / `sla_band_color` resolvers so the palette can
    change in one place. (The existing color-dict-from-import pattern
    `from ... import SEVERITY_COLORS` is allowed — it's the .get() /
    [...] direct-access pattern that's flagged.)"""

    def test_no_page_reimplements_inline_severity_color_dict(self):
        # Look for `colors = {"high": "#dc2626", ...}` style inline
        # severity dicts that drift apart over time. A page that needs
        # severity colors should call `severity_color()`.
        # Allow the pattern in the chart `color_discrete_map=SEVERITY_COLORS`
        # (charts need a dict for plotly); just flag standalone declarations.
        offenders: list[str] = []
        sev_dict_re = re.compile(
            r'\s+=\s+\{[^}]*["\']high["\']\s*:\s*["\']#[0-9a-fA-F]{6}["\'][^}]*'
            r'["\']medium["\']\s*:\s*["\']#[0-9a-fA-F]{6}["\']',
            re.DOTALL,
        )
        for f in sorted(PAGES_DIR.glob("*.py")):
            if f.name == "__init__.py":
                continue
            body = f.read_text(encoding="utf-8")
            if sev_dict_re.search(body):
                offenders.append(f.name)
        # Phase E follow-up shipped (2026-04-28) — the ALLOWED set is
        # now empty. All 7 previously-flagged pages migrated to the
        # severity_color() / risk_color() resolvers in components.py.
        # Empty set means any new inline color dict will fail this test.
        ALLOWED: set[str] = set()
        new_offenders = sorted(set(offenders) - ALLOWED)
        assert not new_offenders, (
            "These pages reintroduced inline severity/risk color dicts — "
            "use severity_color() or risk_color() from components.py:\n  "
            + "\n  ".join(new_offenders)
        )


class TestColorResolvers:
    """The severity_color / sla_band_color / risk_color resolvers in
    components.py are now the single source of truth. These tests
    catch silent renames or accidental removals."""

    COMPONENTS = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"

    def test_severity_color_defined(self):
        body = self.COMPONENTS.read_text(encoding="utf-8")
        assert "def severity_color(" in body

    def test_sla_band_color_defined(self):
        body = self.COMPONENTS.read_text(encoding="utf-8")
        assert "def sla_band_color(" in body

    def test_risk_color_defined(self):
        body = self.COMPONENTS.read_text(encoding="utf-8")
        assert "def risk_color(" in body

    def test_risk_rating_colors_constant_present(self):
        body = self.COMPONENTS.read_text(encoding="utf-8")
        assert "RISK_RATING_COLORS" in body
        # Cover the three known levels + the unknown sentinel.
        for key in ("high", "medium", "low", "unknown"):
            assert f'"{key}"' in body
