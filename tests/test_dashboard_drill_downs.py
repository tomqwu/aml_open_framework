"""Phase C — cross-page drill-downs / deep links.

Source-level checks that the 5 pages in scope:
  - import the navigation helpers from `dashboard.components` /
    `dashboard.query_params`
  - register the expected `link_to_page` / `selectable_dataframe` /
    `read_param` / `consume_param` calls
  - destination pages read the same `selected_<key>` namespace that
    source pages write into via either helper

PR-A (2026-04-29) replaced the "selectbox-below-the-table" pattern on
Alert Queue / Customer 360 / My Queue / Investigations / BOI Workflow
with row-click drill-through via `selectable_dataframe(drill_target=...,
drill_param=..., drill_column=...)`. Tests below accept either form on
the migrated pages — both ultimately mirror into `selected_<param>`.

Avoids importing Streamlit (not on the unit-test CI image).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"

EXEC_DASH = PAGES / "1_Executive_Dashboard.py"
ALERT_QUEUE = PAGES / "3_Alert_Queue.py"
CASE_INV = PAGES / "4_Case_Investigation.py"
NETWORK = PAGES / "10_Network_Explorer.py"
CUSTOMER_360 = PAGES / "17_Customer_360.py"


# ---------------------------------------------------------------------------
# Source pages — write deep-link state via `link_to_page`
# ---------------------------------------------------------------------------


class TestAlertQueueDrillDowns:
    def test_imports_drill_helper(self):
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        assert "from aml_framework.dashboard.components import" in body
        # Either the legacy link_to_page helper or the PR-A row-click
        # helper is acceptable — both mirror to `selected_<param>`.
        assert ("link_to_page" in body) or ("selectable_dataframe" in body)

    def test_links_to_customer_360_with_customer_id(self):
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        # The customer drill must target the Customer 360 page and
        # forward the `customer_id` param so destination can pre-select.
        assert "pages/17_Customer_360.py" in body
        # Either the legacy `customer_id=...` kwarg form (link_to_page)
        # or the row-click form (`drill_param="customer_id"`) is OK.
        assert ('drill_param="customer_id"' in body) or ("customer_id=" in body)

    def test_links_to_case_investigation_with_case_id(self):
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        assert "pages/4_Case_Investigation.py" in body
        assert ('drill_param="case_id"' in body) or ("case_id=" in body)

    def test_drill_is_table_native_or_below_table(self):
        # Either the table itself is the drill (selectable_dataframe row
        # click — preferred since PR-A) or there's a "Drill into ..."
        # selectbox after the alert dataframe. Both should work — the
        # invariant is that the alert table is followed by some drill
        # surface, not just dead-end on the read-only frame.
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        has_row_click = "selectable_dataframe(" in body and 'drill_target="pages/' in body
        has_legacy = (
            "Drill into customer" in body
            and "st.dataframe(styled" in body
            and body.find("Drill into customer") > body.find("st.dataframe(styled")
        )
        assert has_row_click or has_legacy, (
            "Alert Queue must give analysts SOME path off a row — "
            "either row-click (selectable_dataframe) or selectbox-below-table"
        )


class TestNetworkExplorerDrillDown:
    def test_imports_link_to_page(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "link_to_page" in body

    def test_node_drill_links_to_customer_360(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "pages/17_Customer_360.py" in body
        assert "customer_id=" in body

    def test_drill_defaults_to_alerted_node_when_present(self):
        # Alerted nodes are the highest-value drill target; the default
        # should bias toward them so analysts get there in one click.
        body = NETWORK.read_text(encoding="utf-8")
        assert "alerted_ids" in body
        # The default-node logic should reference alerted_ids in the
        # same statement as the index lookup.
        idx = body.find("default_node")
        assert idx > 0
        snippet = body[idx : idx + 500]
        assert "alerted_ids" in snippet


class TestExecutiveDashboardKpiDrillDowns:
    def test_imports_link_to_page(self):
        body = EXEC_DASH.read_text(encoding="utf-8")
        assert "link_to_page" in body

    def test_links_to_alert_queue(self):
        body = EXEC_DASH.read_text(encoding="utf-8")
        assert "pages/3_Alert_Queue.py" in body

    def test_links_to_investigations(self):
        body = EXEC_DASH.read_text(encoding="utf-8")
        assert "pages/24_Investigations.py" in body


# ---------------------------------------------------------------------------
# Destination pages — read the deep-link state via query_params helpers
# ---------------------------------------------------------------------------


class TestCustomer360ReceivesDeepLink:
    def test_imports_query_params_helper(self):
        body = CUSTOMER_360.read_text(encoding="utf-8")
        assert "from aml_framework.dashboard.query_params import" in body
        assert "read_param" in body

    def test_uses_customer_id_param(self):
        body = CUSTOMER_360.read_text(encoding="utf-8")
        # Page must read the `customer_id` param + use it to default the
        # selectbox so deep links from Alert Queue / Network Explorer
        # actually pre-select the row.
        assert 'read_param("customer_id")' in body
        assert "default_cid_idx" in body
        assert "index=default_cid_idx" in body

    def test_per_case_drill_to_case_investigation(self):
        body = CUSTOMER_360.read_text(encoding="utf-8")
        assert "pages/4_Case_Investigation.py" in body
        # Same dual acceptance as Alert Queue — legacy kwarg or row-click.
        assert ('drill_param="case_id"' in body) or ("case_id=" in body)


class TestCaseInvestigationReceivesDeepLink:
    def test_consumes_case_id_param(self):
        # Case Investigation must consume (not just read) the param so a
        # page refresh doesn't infinite-redirect.
        body = CASE_INV.read_text(encoding="utf-8")
        assert 'consume_param("case_id")' in body


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


class TestDrillDownInvariants:
    def test_no_page_uses_inline_anchor_tag_for_navigation(self):
        # All drill-downs flow through link_to_page; raw `<a href>` for
        # in-app nav is forbidden because it bypasses the session-state
        # mirror the destination pages depend on.
        for page in (ALERT_QUEUE, NETWORK, EXEC_DASH, CUSTOMER_360):
            body = page.read_text(encoding="utf-8")
            # Allow `<a>` for external links (CSS/HTML blocks); flag only
            # in-app navigation patterns.
            assert '<a href="./pages/' not in body, f"{page.name} uses raw <a> for in-app nav"

    def test_session_state_namespace_is_consistent(self):
        # link_to_page writes to `selected_<key>`; destination reads via
        # read_param/consume_param which use the same key. If a page
        # reaches into st.session_state directly it MUST use the same
        # `selected_<key>` prefix.
        for page in (CUSTOMER_360, CASE_INV):
            body = page.read_text(encoding="utf-8")
            # The pages should NOT introduce a parallel namespace like
            # `deep_link_*` or `param_*` directly in session_state.
            assert "st.session_state['param_" not in body
            assert 'st.session_state["param_' not in body

    def test_destination_pages_default_gracefully_when_no_param(self):
        # If no deep link is set, default_idx should be 0 (or the page's
        # native first-option behavior) — never raise.
        cust = CUSTOMER_360.read_text(encoding="utf-8")
        # The pattern: `customer_ids.index(deep_link_cid) if ... else 0`
        assert "else 0" in cust
        case = CASE_INV.read_text(encoding="utf-8")
        assert "else 0" in case
