"""Spec Editor -- edit and validate aml.yaml in the browser."""

from __future__ import annotations

import streamlit as st
import yaml

from aml_framework.dashboard.components import kpi_card, page_header

page_header(
    "Spec Editor",
    "Edit the AML spec YAML and validate in real time.",
)

spec = st.session_state.spec
spec_path = st.session_state.spec_path

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Spec Editor**\n\n"
        "Edit the spec YAML below and click **Validate** to check for errors. "
        "This does not modify the file on disk — use it to prototype changes "
        "before committing to your spec repository."
    )

# Load current spec content.
try:
    current_yaml = spec_path.read_text(encoding="utf-8")
except Exception:
    current_yaml = "# Could not load spec file"

# --- Interactive Rule Builder ---
with st.expander("Rule Builder — create a new rule interactively"):
    rb_col1, rb_col2 = st.columns(2)
    with rb_col1:
        rb_id = st.text_input("Rule ID", value="new_rule", help="Unique identifier (snake_case)")
        rb_name = st.text_input("Rule Name", value="New Detection Rule")
        rb_severity = st.selectbox("Severity", ["low", "medium", "high", "critical"], index=1)
        rb_status = st.selectbox("Status", ["active", "draft", "disabled"], index=0)
        rb_escalate = st.selectbox(
            "Escalate to",
            [q.id for q in spec.workflow.queues],
            index=0,
        )
    with rb_col2:
        rb_type = st.selectbox(
            "Logic Type",
            ["aggregation_window", "custom_sql", "list_match", "python_ref"],
            index=0,
        )
        rb_source = st.selectbox(
            "Source Table",
            [c.id for c in spec.data_contracts],
            index=0,
        )
        if rb_type == "aggregation_window":
            rb_window = st.text_input("Window", value="30d", help="e.g. 30d, 24h, 7d")
            rb_group = st.text_input("Group By", value="customer_id")
            rb_having = st.text_input("Having (JSON)", value='{"sum_amount": {"gte": 10000}}')
        elif rb_type == "custom_sql":
            rb_sql_template = st.text_area(
                "SQL Template",
                value="SELECT customer_id, SUM(amount) AS sum_amount\nFROM {source}\nWHERE booked_at >= TIMESTAMP '{window_start}'\nGROUP BY customer_id\nHAVING SUM(amount) >= 10000",
                height=120,
            )
        elif rb_type == "list_match":
            rb_list = st.text_input(
                "List Name", value="sanctions", help="CSV file name in data/lists/"
            )
            rb_field = st.text_input("Match Field", value="full_name")
            rb_match = st.selectbox("Match Type", ["exact", "fuzzy"])
        elif rb_type == "python_ref":
            rb_callable = st.text_input(
                "Callable", value="aml_framework.models.scoring:heuristic_risk_scorer"
            )
            rb_model_id = st.text_input("Model ID", value="risk_scorer_v1")

    # Generate YAML snippet.
    if st.button("Generate Rule YAML"):
        import json as _json

        snippet_lines = [
            f"  - id: {rb_id}",
            f'    name: "{rb_name}"',
            f"    severity: {rb_severity}",
            f"    status: {rb_status}",
            f"    escalate_to: {rb_escalate}",
            "    evidence: []",
            "    regulation_refs: []",
            "    logic:",
        ]
        if rb_type == "aggregation_window":
            snippet_lines.extend(
                [
                    "      type: aggregation_window",
                    f"      source: {rb_source}",
                    f"      window: {rb_window}",
                    f"      group_by: [{rb_group}]",
                ]
            )
            try:
                having = _json.loads(rb_having)
                for k, v in having.items():
                    if isinstance(v, dict):
                        for op, val in v.items():
                            snippet_lines.append("      having:")
                            snippet_lines.append(f"        {k}:")
                            snippet_lines.append(f"          {op}: {val}")
                            break
                    else:
                        snippet_lines.append("      having:")
                        snippet_lines.append(f"        {k}: {v}")
            except _json.JSONDecodeError:
                snippet_lines.append(f"      having: {rb_having}")
        elif rb_type == "custom_sql":
            snippet_lines.extend(
                [
                    "      type: custom_sql",
                    f"      source: {rb_source}",
                    "      sql: |",
                ]
            )
            for sql_line in rb_sql_template.splitlines():
                snippet_lines.append(f"        {sql_line}")
        elif rb_type == "list_match":
            snippet_lines.extend(
                [
                    "      type: list_match",
                    f"      source: {rb_source}",
                    f"      list: {rb_list}",
                    f"      field: {rb_field}",
                    f"      match: {rb_match}",
                ]
            )
        elif rb_type == "python_ref":
            snippet_lines.extend(
                [
                    "      type: python_ref",
                    f'      callable: "{rb_callable}"',
                    f"      model_id: {rb_model_id}",
                    '      model_version: "1.0"',
                ]
            )

        snippet = "\n".join(snippet_lines)
        st.code(snippet, language="yaml")
        st.caption("Copy this snippet and paste it into the rules section of your spec below.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Editor ---
st.markdown("### YAML Editor")
edited_yaml = st.text_area(
    "Edit spec",
    value=current_yaml,
    height=500,
    label_visibility="collapsed",
)

# --- Validation ---
col_v1, col_v2 = st.columns([1, 3])
with col_v1:
    validate_btn = st.button("Validate", type="primary", use_container_width=True)

if validate_btn:
    try:
        # Parse YAML.
        parsed = yaml.safe_load(edited_yaml)
        if not parsed:
            st.error("Empty YAML.")
        else:
            # Validate against schema + Pydantic.
            import tempfile
            from pathlib import Path

            from aml_framework.spec.loader import load_spec

            # Write to temp file for validation.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as f:
                f.write(edited_yaml)
                tmp_path = Path(f.name)

            try:
                validated_spec = load_spec(tmp_path)
                st.success(
                    f"Valid spec: **{validated_spec.program.name}** — "
                    f"{len(validated_spec.rules)} rules, "
                    f"{len(validated_spec.metrics)} metrics, "
                    f"{len(validated_spec.workflow.queues)} queues."
                )

                # Show summary.
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    kpi_card("Rules", len(validated_spec.rules), "#2563eb")
                with c2:
                    kpi_card("Metrics", len(validated_spec.metrics), "#059669")
                with c3:
                    kpi_card("Queues", len(validated_spec.workflow.queues), "#7c3aed")
                with c4:
                    kpi_card("Reports", len(validated_spec.reports), "#d97706")

                # Show rules.
                st.markdown("### Rules")
                for rule in validated_spec.rules:
                    st.markdown(
                        f"- **{rule.id}** ({rule.severity}) — {rule.name} [{rule.logic.type}]"
                    )
            except ValueError as e:
                st.error(f"Validation failed:\n\n{e}")
            finally:
                tmp_path.unlink(missing_ok=True)
    except yaml.YAMLError as e:
        st.error(f"YAML parse error:\n\n{e}")

# --- Diff ---
st.markdown("<br>", unsafe_allow_html=True)
if edited_yaml != current_yaml:
    st.warning("Spec has been modified (not saved to disk).")
    with st.expander("Show changes"):
        import difflib

        diff = difflib.unified_diff(
            current_yaml.splitlines(keepends=True),
            edited_yaml.splitlines(keepends=True),
            fromfile="original",
            tofile="edited",
        )
        st.code("".join(diff), language="diff")
