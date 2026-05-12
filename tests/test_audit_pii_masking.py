"""PII masking policy layer tests (PR 18.9).

Opt-in via `AML_PII_MASKING=1`. When enabled, the audit ledger
hashes the values of any alert/case field whose key matches a
`pii: true` column in the spec's data_contracts, and records a
(hash, plaintext) sidecar at `pii_map.jsonl` for regulator-only
unmask via `unmask_alerts(run_dir)`.

Tests pin: opt-out is the default (existing behavior unchanged),
mask-on-write produces hashes + sidecar, unmask round-trips,
non-PII fields are untouched.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.engine.audit import (
    _pii_columns_from_spec,
    _pii_mask_value,
    unmask_alerts,
)
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _run_with_masking(tmp_path: Path, *, masking: bool) -> Path:
    """Run the canadian spec on synthetic data with masking either on
    or off. Returns the run_dir path so tests can inspect artifacts."""
    import os

    spec = load_spec(SPEC_CA)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    prior = os.environ.get("AML_PII_MASKING")
    try:
        if masking:
            os.environ["AML_PII_MASKING"] = "1"
        else:
            os.environ.pop("AML_PII_MASKING", None)
        run_spec(spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path)
    finally:
        if prior is None:
            os.environ.pop("AML_PII_MASKING", None)
        else:
            os.environ["AML_PII_MASKING"] = prior
    # run_spec writes to artifacts_root/run-<ts>; return the only run dir.
    runs = sorted((tmp_path).glob("run-*"))
    assert runs, "expected at least one run directory"
    # Use the latest run (in case the tmp_path has multiple).
    return runs[-1]


class TestPiiColumnDiscovery:
    def test_canadian_spec_marks_customer_id_pii(self):
        spec = load_spec(SPEC_CA)
        pii = _pii_columns_from_spec(spec)
        # `pii: true` is set on customer_id + full_name (and possibly
        # others) per the canadian spec data_contracts.
        assert "customer_id" in pii, f"expected customer_id in pii cols; got {pii}"


class TestMaskOnWriteOptOutDefault:
    """When `AML_PII_MASKING` is unset (the default), alerts.jsonl
    is unchanged — no hashing, no sidecar. Critical so existing test
    fixtures and dashboards stay byte-identical."""

    def test_masking_off_writes_plaintext_alerts(self, tmp_path):
        run_dir = _run_with_masking(tmp_path, masking=False)
        alerts_files = list((run_dir / "alerts").glob("*.jsonl"))
        # Find one with content to inspect.
        nonempty = [p for p in alerts_files if p.read_text().strip()]
        assert nonempty, "expected at least one non-empty alerts.jsonl"
        # No customer_id should look like a 16-char hex hash.
        sample = json.loads(nonempty[0].read_text().splitlines()[0])
        cid = sample.get("customer_id", "")
        assert not (len(cid) == 16 and all(c in "0123456789abcdef" for c in cid)), (
            f"customer_id looks pre-hashed: {cid!r}"
        )

    def test_masking_off_omits_sidecar(self, tmp_path):
        run_dir = _run_with_masking(tmp_path, masking=False)
        sidecar = run_dir / "pii_map.jsonl"
        # Either absent or empty — both are fine for the "no masking" path.
        assert not sidecar.exists() or sidecar.stat().st_size == 0


class TestMaskOnWriteEnabled:
    def test_masking_on_replaces_pii_values_with_hashes(self, tmp_path):
        run_dir = _run_with_masking(tmp_path, masking=True)
        alerts_files = list((run_dir / "alerts").glob("*.jsonl"))
        nonempty = [p for p in alerts_files if p.read_text().strip()]
        assert nonempty
        for path in nonempty:
            for line in path.read_text().splitlines():
                alert = json.loads(line)
                cid = alert.get("customer_id")
                if cid:
                    assert len(cid) == 16 and all(c in "0123456789abcdef" for c in cid), (
                        f"expected 16-hex hash, got {cid!r}"
                    )

    def test_masking_on_writes_sidecar_with_plaintext(self, tmp_path):
        run_dir = _run_with_masking(tmp_path, masking=True)
        sidecar = run_dir / "pii_map.jsonl"
        assert sidecar.exists(), "expected pii_map.jsonl when masking is on"
        rows = [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
        assert rows, "expected at least one (hash, plaintext) row"
        for row in rows:
            assert set(row.keys()) == {"field", "hash", "plaintext"}
            # Hash must reproduce given the dev salt.
            from aml_framework.engine.audit import _pii_salt

            assert row["hash"] == _pii_mask_value(row["plaintext"], _pii_salt())

    def test_unmask_round_trips_plaintext(self, tmp_path):
        run_dir = _run_with_masking(tmp_path, masking=True)
        unmasked = unmask_alerts(run_dir)
        assert unmasked, "expected alerts dict"
        # At least one rule should have alerts with plaintext
        # customer_ids (matching the C0### format the synthetic
        # generator uses).
        any_match = False
        for rule_id, alerts in unmasked.items():
            for alert in alerts:
                cid = alert.get("customer_id", "")
                if cid.startswith("C0"):
                    any_match = True
                    break
        assert any_match, "expected at least one alert with unmasked C0### customer_id"

    def test_non_pii_fields_unchanged_under_masking(self, tmp_path):
        """`sum_amount`, `count`, `window_start` etc. aren't PII —
        masking must leave them untouched."""
        run_dir = _run_with_masking(tmp_path, masking=True)
        alerts_files = list((run_dir / "alerts").glob("*.jsonl"))
        nonempty = [p for p in alerts_files if p.read_text().strip()]
        for path in nonempty:
            for line in path.read_text().splitlines():
                alert = json.loads(line)
                # sum_amount must remain a number, not a string hash.
                if "sum_amount" in alert:
                    assert isinstance(alert["sum_amount"], (int, float, str))
                    # If string, it must look like a number not a hash.
                    if isinstance(alert["sum_amount"], str):
                        # Numbers serialize as e.g. "1234.56", not 16-hex.
                        v = alert["sum_amount"]
                        is_hash = len(v) == 16 and all(c in "0123456789abcdef" for c in v)
                        assert not is_hash, f"sum_amount got hashed: {v!r}"
