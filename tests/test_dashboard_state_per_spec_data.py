"""Dashboard data-resolution: registered specs use their per-spec band (#522).

The root ``data/input/{txn,customer}.csv`` files are the community-bank
shape. They MUST NOT shadow a spec that has its own planted-positive
generator, or ``aml dashboard examples/us_rtp_fednow/aml.yaml`` would
show community-bank data instead of the spec's C9xxx band.

These tests are streamlit-free (unit CI installs only ``[dev]`` and the
project's lazy-import rule forbids importing ``streamlit`` here). They
pin:

1. the registry-membership predicate the dashboard branch uses, and
2. (source-level) that ``dashboard/state.py`` actually gates its
   root-CSV preference on ``not has_registered_generator(spec)``, so a
   registered spec falls through to its per-spec generator, and
3. that the engine-run path (``resolve_source("synthetic", spec, ...)``)
   the dashboard must now mirror yields the C9xxx band for a registered
   spec.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aml_framework.data import has_registered_generator
from aml_framework.data.sources import resolve_source
from aml_framework.spec.loader import load_spec

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
_ROOT = Path(__file__).resolve().parents[1]
_STATE_PY = _ROOT / "src" / "aml_framework" / "dashboard" / "state.py"
AS_OF = datetime(2026, 6, 1, 12, 0, 0)


def test_registered_predicate_matches_the_three_newer_specs() -> None:
    for name in ("us_rtp_fednow", "uk_app_fraud", "trade_based_ml"):
        assert has_registered_generator(load_spec(_EXAMPLES / name / "aml.yaml"))
    # Community-bank + another unregistered spec keep today's behaviour.
    for name in ("community_bank", "eu_bank"):
        assert not has_registered_generator(load_spec(_EXAMPLES / name / "aml.yaml"))


def test_root_csvs_exist_so_the_shadowing_risk_is_real() -> None:
    # If these ever move, the dashboard branch this guards is moot — fail
    # loudly so the test is re-pointed rather than silently passing.
    assert (_ROOT / "data" / "input" / "txn.csv").exists()
    assert (_ROOT / "data" / "input" / "customer.csv").exists()


def test_state_gates_root_csv_preference_on_registry_membership() -> None:
    """Source-level guard for the dashboard fix (streamlit-free).

    The root-CSV preference branch in ``initialize_session`` must be
    gated on ``not has_registered_generator(spec)``; otherwise registered
    specs would be shadowed by the community-bank root CSVs. A runtime
    test would have to import streamlit (forbidden in unit CI by the
    lazy-import rule), so this asserts the gate at the source level.
    """
    src = _STATE_PY.read_text(encoding="utf-8")
    assert "has_registered_generator" in src
    # The CSV-preference conjunction starts with the registry guard.
    assert "csv_files_present = (\n        not has_registered_generator(spec)" in src


def test_resolve_source_synthetic_yields_per_spec_band_for_registered_spec() -> None:
    """The engine-run path the dashboard now mirrors for registered specs.

    ``aml dashboard`` (registered spec) falls through to the same
    ``generate_dataset_for_spec`` path ``aml run`` uses. This asserts that
    path serves the dedicated C9xxx band, not the community-bank C0xxx
    dataset.
    """
    spec = load_spec(_EXAMPLES / "us_rtp_fednow" / "aml.yaml")
    data = resolve_source(source_type="synthetic", spec=spec, as_of=AS_OF, seed=42)
    ids = {c["customer_id"] for c in data["customer"]}
    assert "C9001" in ids and "C9029" in ids
    assert not any(cid.startswith("C00") for cid in ids)
