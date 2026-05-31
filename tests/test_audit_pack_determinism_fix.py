"""Regression: the audit pack must be byte-deterministic (no wall-clock).

`_audit_trail_verification` used to embed `datetime.now()` as `verified_at`,
so two `build_audit_pack` calls that straddled a one-second boundary produced
different bytes — an intermittent failure of the determinism guarantee
(surfaced as flaky `TestDeterminism` runs in the Docker/CI suite). These
tests pin that the verification block is a pure function of the decisions and
that no wall-clock leaks into the built bundle.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from aml_framework.generators.audit_pack import _audit_trail_verification, build_audit_pack
from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def test_audit_trail_verification_is_pure_and_has_no_wallclock():
    decisions = [{"hash": "a", "prev_hash": ""}, {"hash": "b", "prev_hash": "a"}]
    r1 = _audit_trail_verification(decisions)
    r2 = _audit_trail_verification(decisions)
    assert r1 == r2, "verification must be a pure function of the decisions"
    assert "verified_at" not in r1, "no wall-clock field in a deterministic artifact"
    assert r1["chain_intact"] is True
    assert r1["chain_length"] == 2


def test_built_pack_verification_json_has_no_wallclock():
    spec = load_spec(SPEC)
    payload = build_audit_pack(spec, cases=[], decisions=[])
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if n.endswith("audit_trail_verification.json")]
        assert names, "audit_trail_verification.json should be in the bundle"
        data = json.loads(zf.read(names[0]))
    assert "verified_at" not in data
    assert "chain_intact" in data


def test_audit_pack_bytes_stable_across_builds():
    # Back-to-back builds must be byte-identical (the determinism guarantee).
    spec = load_spec(SPEC)
    assert build_audit_pack(spec, cases=[], decisions=[]) == build_audit_pack(
        spec, cases=[], decisions=[]
    )
