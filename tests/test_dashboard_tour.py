"""Tests for the guided-tour state machine + integration wiring.

The state-machine layer (``dashboard/tour.py``) is pure-python and
tested with plain dicts in place of session_state. The UI layer
(``components.tour_panel``) is verified via source-level assertions
since it uses streamlit at call time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aml_framework.dashboard import tour as tour_mod

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = PROJECT_ROOT / "src" / "aml_framework" / "dashboard"


# ---------------------------------------------------------------------------
# Tour arc shape — invariants the analyst arc must hold
# ---------------------------------------------------------------------------


class TestAnalystArc:
    def test_analyst_arc_has_steps(self):
        assert len(tour_mod.ANALYST_ARC) >= 4, "Analyst arc must be at least 4 steps"

    def test_each_step_targets_an_existing_page(self):
        for step in tour_mod.ANALYST_ARC:
            page_file = DASHBOARD / step.page_path
            assert page_file.exists(), (
                f"Step {step.step_title!r} targets {step.page_path!r} but the file "
                f"doesn't exist — did the page get renamed/removed?"
            )

    def test_each_step_has_required_fields(self):
        for step in tour_mod.ANALYST_ARC:
            assert step.page_path
            assert step.page_title
            assert step.step_title
            assert step.narrative and len(step.narrative) > 50, (
                "Step narrative should be at least a sentence"
            )
            assert step.task
            assert step.duration

    def test_no_duplicate_pages_in_arc(self):
        paths = [s.page_path for s in tour_mod.ANALYST_ARC]
        assert len(paths) == len(set(paths)), "Same page appears twice in arc — re-order"


class TestTourArcsRegistry:
    def test_known_arcs_present(self):
        # Manager / CCO / Auditor are placeholders for follow-up PRs but
        # must be in the registry so the dropdown can list them.
        for arc_id in ("analyst", "manager", "cco", "auditor"):
            assert arc_id in tour_mod.TOUR_ARCS

    def test_only_analyst_is_populated_in_v1(self):
        # Sanity check — if someone adds steps to manager/cco/auditor
        # without writing the matching tests, this fails.
        assert len(tour_mod.ANALYST_ARC) > 0
        assert len(tour_mod.MANAGER_ARC) == 0, (
            "Manager arc should be empty in v1 — implementing it requires its own test pass"
        )
        assert len(tour_mod.CCO_ARC) == 0
        assert len(tour_mod.AUDITOR_ARC) == 0

    def test_labels_present_for_all_arcs(self):
        for arc_id in tour_mod.TOUR_ARCS:
            assert arc_id in tour_mod.TOUR_LABELS


# ---------------------------------------------------------------------------
# State-machine semantics
# ---------------------------------------------------------------------------


class TestStartTour:
    def test_start_sets_active_state(self):
        state = {}
        tour_mod.start(state, "analyst")
        assert state["tour_active"] is True
        assert state["tour_arc"] == "analyst"
        assert state["tour_step"] == 0

    def test_start_unknown_arc_raises(self):
        with pytest.raises(ValueError, match="Unknown tour arc"):
            tour_mod.start({}, "no_such_persona")


class TestAdvance:
    def test_advance_moves_forward(self):
        state = {}
        tour_mod.start(state, "analyst")
        original_step = state["tour_step"]
        nxt = tour_mod.advance(state)
        assert nxt is not None
        assert state["tour_step"] == original_step + 1
        assert nxt is tour_mod.ANALYST_ARC[1]

    def test_advance_off_inactive_returns_none(self):
        state = {}
        assert tour_mod.advance(state) is None

    def test_advance_past_end_marks_complete(self):
        state = {}
        tour_mod.start(state, "analyst")
        for _ in range(len(tour_mod.ANALYST_ARC)):
            tour_mod.advance(state)
        # We've advanced past the last index → returned None on last call,
        # but the tour should be marked complete.
        assert tour_mod.is_complete(state)
        assert tour_mod.current_step(state) is None


class TestRetreat:
    def test_retreat_moves_back(self):
        state = {}
        tour_mod.start(state, "analyst")
        tour_mod.advance(state)  # step 1
        prev = tour_mod.retreat(state)
        assert prev is tour_mod.ANALYST_ARC[0]
        assert state["tour_step"] == 0

    def test_retreat_at_first_step_stays(self):
        state = {}
        tour_mod.start(state, "analyst")
        prev = tour_mod.retreat(state)
        assert prev is None
        # Step should not go negative.
        assert state["tour_step"] == 0


class TestEnd:
    def test_end_clears_state(self):
        state = {"tour_active": True, "tour_arc": "analyst", "tour_step": 2}
        tour_mod.end(state)
        assert "tour_active" not in state
        assert "tour_arc" not in state
        assert "tour_step" not in state


class TestCurrentStep:
    def test_returns_step_when_active(self):
        state = {}
        tour_mod.start(state, "analyst")
        assert tour_mod.current_step(state) is tour_mod.ANALYST_ARC[0]

    def test_returns_none_when_inactive(self):
        state = {}
        assert tour_mod.current_step(state) is None

    def test_returns_none_when_arc_empty(self):
        # Manager arc is empty in v1 — selecting it should not show a step.
        state = {}
        tour_mod.start(state, "manager")
        assert tour_mod.current_step(state) is None


class TestStepPosition:
    def test_returns_one_indexed_count(self):
        state = {}
        tour_mod.start(state, "analyst")
        cur, total = tour_mod.step_position(state)
        assert cur == 1
        assert total == len(tour_mod.ANALYST_ARC)
        tour_mod.advance(state)
        cur, total = tour_mod.step_position(state)
        assert cur == 2


# ---------------------------------------------------------------------------
# Source-level wiring assertions
# ---------------------------------------------------------------------------


COMPONENTS_FILE = DASHBOARD / "components.py"
APP_FILE = DASHBOARD / "app.py"


class TestComponentsHelpers:
    def test_tour_panel_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def tour_panel(" in body

    def test_tooltip_banner_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def tooltip_banner(" in body

    def test_tour_panel_imports_tour_module(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Should import via dashboard.tour, not redefine state shape.
        assert "from aml_framework.dashboard import tour" in body

    def test_tour_panel_renders_step_counter(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Step N / M format must be in the rendered HTML so users know
        # where they are in the arc.
        m = re.search(r"STEP\s*\{cur\}\s*/\s*\{total\}", body)
        assert m, "tour_panel should render 'STEP N / M' counter"

    def test_tour_panel_has_back_skip_next_buttons(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The three required navigation actions.
        assert '"← Back"' in body or "Back" in body
        assert "Skip tour" in body
        assert "Next →" in body or "Finish ✓" in body


class TestSidebarWiring:
    def test_app_uses_guided_mode_dropdown(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # The legacy boolean toggle was replaced with a select; verify
        # the new state shape exists.
        assert "guided_mode" in body, "app.py should set guided_mode in session state"
        assert "tour_mod.start" in body or "tour.start" in body, (
            "app.py should kick off tours via the tour module"
        )

    def test_legacy_guided_demo_compat_preserved(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # Legacy `guided_demo` flag should still be set when mode is
        # "tooltip" so unmigrated pages keep working.
        assert "guided_demo" in body


# ---------------------------------------------------------------------------
# Page wiring — the 5 analyst-arc pages must call tour_panel(page_title)
# ---------------------------------------------------------------------------


class TestAnalystArcPagesWired:
    @pytest.mark.parametrize(
        "page_path,page_title",
        [
            ("pages/3_Alert_Queue.py", "Alert Queue"),
            ("pages/4_Case_Investigation.py", "Case Investigation"),
            ("pages/17_Customer_360.py", "Customer 360"),
            ("pages/7_Audit_Evidence.py", "Audit & Evidence"),
            ("pages/8_Framework_Alignment.py", "Framework Alignment"),
        ],
    )
    def test_page_calls_tour_panel(self, page_path: str, page_title: str):
        body = (DASHBOARD / page_path).read_text(encoding="utf-8")
        # Match either tour_panel("X") or tour_panel('X')
        m = re.search(rf"tour_panel\(\s*[\'\"]{re.escape(page_title)}[\'\"]\s*\)", body)
        assert m, (
            f"Page {page_path} doesn't call tour_panel({page_title!r}); the "
            f"tour panel won't render when the user is on this step."
        )

    @pytest.mark.parametrize(
        "page_path",
        [
            "pages/3_Alert_Queue.py",
            "pages/4_Case_Investigation.py",
            "pages/17_Customer_360.py",
            "pages/7_Audit_Evidence.py",
            "pages/8_Framework_Alignment.py",
        ],
    )
    def test_page_no_longer_uses_legacy_st_info_for_guided_demo(self, page_path: str):
        body = (DASHBOARD / page_path).read_text(encoding="utf-8")
        # The pre-tour pattern was `if st.session_state.get("guided_demo"): st.info(...)`.
        # Migration replaces it with tour_panel + tooltip_banner. The legacy
        # check shouldn't appear anymore on the migrated pages.
        assert 'st.session_state.get("guided_demo")' not in body, (
            f"{page_path} still has legacy guided_demo check — should use "
            "tour_panel + tooltip_banner instead"
        )
