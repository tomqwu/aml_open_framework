"""Information Sharing — cross-bank obfuscated-pattern exchange surface (PR-DATA-10b).

Backs the "Data is the AML problem" whitepaper's DATA-10 reference
surface for FATF R.18 / Wolfsberg CBDDQ / FinCEN 314(b) / AMLA
cross-border information sharing. Renders the spec's
`information_sharing` block — partners declared, scope, salt-rotation
cadence — and the recent share-pattern artifacts produced by the
`aml share-pattern` CLI.

This is a **read-only operational view**. Production cross-FI exchange
requires partner agreements, salt-rotation infrastructure, and
regulator approval — out of scope for the framework. The page exists so
an MLRO / auditor can see at a glance which partnerships the spec
declares, which salts have been rotated when, and what overlap
findings have been verified.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import data_grid, empty_state, page_header

page_header(
    "Information Sharing",
    "Cross-bank obfuscated-pattern exchange · FATF R.18 / Wolfsberg CBDDQ / 314(b)",
)
show_audience_context("Information Sharing")

spec = st.session_state.spec

# --- Empty-state guard: spec must declare information_sharing ----------------
info = getattr(spec, "information_sharing", None)
if info is None or not info.enabled:
    empty_state(
        "Information sharing is not enabled in this spec.",
        icon="🔒",
        detail=(
            "Add an `information_sharing` block to your `aml.yaml`, set "
            "`enabled: true`, and list partner FIs. The framework's "
            "`compliance/sandbox.py` consumes this block via "
            "`aml share-pattern --partner <fi_id> --salt <secret>`. "
            "See [`docs/research/2026-05-aml-data-problem.md`](https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-05-aml-data-problem.md) "
            "DATA-10 for the regulatory framing."
        ),
        stop=True,
    )

# --- Partner roster ----------------------------------------------------------
st.markdown("### Declared partners")
if info.partners:
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "FI ID": p.fi_id,
                "Label": p.label or "—",
                "Jurisdictions": ", ".join(p.jurisdictions) if p.jurisdictions else "—",
                "Typology scope": ", ".join(p.typology_scope) if p.typology_scope else "—",
                "Salt rotation": p.salt_rotation,
            }
            for p in info.partners
        ]
    )
    data_grid(
        df,
        key="info_sharing_partners",
        pinned_left=["FI ID"] if "FI ID" in df.columns else None,
        height=min(35 * len(df) + 60, 300),
    )
else:
    st.caption("No partners declared yet — add entries under `information_sharing.partners`.")

if info.notes:
    st.markdown(f"**Notes:** {info.notes}")

st.markdown("<br>", unsafe_allow_html=True)

# --- Recent share-pattern artifacts -----------------------------------------
# By convention, `aml share-pattern --out <path>` writes JSON files;
# the dashboard surfaces any *.json file in `share-patterns/` so
# operators see what's been published recently. Skipped if the dir
# doesn't exist (most installs).
st.markdown("### Recent share-pattern artifacts")
share_dir = Path("share-patterns")
if share_dir.exists() and share_dir.is_dir():
    artifacts = sorted(share_dir.glob("*.json"))
    if artifacts:
        rows = []
        for path in artifacts[-10:]:  # last 10
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
                rows.append(
                    {
                        "File": path.name,
                        "Rule family": body.get("rule_family", "—"),
                        "Pattern": body.get("pattern_kind", "—"),
                        "Salt period": body.get("salt_period") or "(unset)",
                        "Subjects": len(body.get("obfuscated_subject_ids", [])),
                        "Neighbours": len(body.get("obfuscated_neighbour_ids", [])),
                        "Detected at": body.get("detected_at", "—"),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                continue
        if rows:
            import pandas as pd

            data_grid(
                pd.DataFrame(rows),
                key="info_sharing_artifacts",
                pinned_left=["File"],
                height=min(35 * len(rows) + 60, 300),
            )
        else:
            st.caption("Found `share-patterns/` directory but no parseable JSON files inside.")
    else:
        st.caption(
            "No share-pattern artifacts yet. Run "
            "`aml share-pattern <spec> --partner <fi_id> --salt <secret>` "
            "to publish one."
        )
else:
    st.caption(
        "No `share-patterns/` directory in the working dir. Run "
        "`aml share-pattern --out share-patterns/<partner>.json …` "
        "to start publishing."
    )

st.markdown("<br>", unsafe_allow_html=True)

# --- How to use this page ---------------------------------------------------
with st.expander("How to use this page", expanded=False):
    st.markdown(
        """
**Workflow:**

1. **Declare partners** in `aml.yaml` under `information_sharing.partners`.
2. **Agree a salt** out-of-band with each partner (e.g. monthly rotation
   via a shared key vault). The salt is what makes obfuscated IDs
   comparable across FIs without leaking the underlying customer IDs.
3. **Publish** an obfuscated pattern: `aml share-pattern <spec>
   --partner <fi_id> --salt <secret> --salt-period 2026-05 --out share-patterns/<partner>.json`.
4. **Verify** when the partner sends back theirs:
   `aml verify-pattern share-patterns/<our>.json share-patterns/<theirs>.json`.

**What's out of scope:** transport (mTLS, message bus), partner
discovery, salt rotation infrastructure, regulator notification.
The framework ships the *reference surface* — the policy boundary
(spec block) and the cryptographic primitives (`compliance/sandbox.py`)
— so an institution can demonstrate posture and integrate against
its own production transport.
        """
    )
