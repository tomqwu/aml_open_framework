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
