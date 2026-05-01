"""Filing-timestamp capture (PR-DATA-9).

Backs the "Data is the AML problem" whitepaper's DATA-9 claim that
"STR filing-latency p95 is a first-class metric" — wall-clock latency
between case-open and actual STR submission, captured via a sidecar
artifact written by `cases.filing.record_filing` and read by
`metrics/engine.py:_proxy_filing_latency`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aml_framework.cases.filing import (
    FilingRecord,
    filing_latency_days,
    filing_path,
    get_filing,
    list_filings,
    record_filing,
)


_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# record_filing / get_filing roundtrip
# ---------------------------------------------------------------------------


class TestFilingSidecar:
    def test_record_then_get_roundtrip(self, tmp_path: Path):
        record_filing(
            tmp_path,
            "C0042",
            filed_at=_AS_OF,
            channel="goaml",
            reference_id="GOAML-XYZ-123",
            notes="initial submission",
        )
        loaded = get_filing(tmp_path, "C0042")
        assert loaded is not None
        assert loaded.case_id == "C0042"
        assert loaded.filed_at == _AS_OF
        assert loaded.channel == "goaml"
        assert loaded.reference_id == "GOAML-XYZ-123"
        assert loaded.notes == "initial submission"

    def test_get_returns_none_when_no_sidecar(self, tmp_path: Path):
        assert get_filing(tmp_path, "C-NEVER-FILED") is None

    def test_record_overwrites_when_filed_at_changes(self, tmp_path: Path):
        # Re-filing with a different timestamp wins; latest wins.
        record_filing(tmp_path, "C0001", filed_at=_AS_OF, channel="goaml")
        record_filing(
            tmp_path,
            "C0001",
            filed_at=_AS_OF + timedelta(hours=2),
            channel="goaml",
            notes="re-submitted after transport error",
        )
        rec = get_filing(tmp_path, "C0001")
        assert rec is not None
        assert rec.filed_at == _AS_OF + timedelta(hours=2)
        assert "re-submitted" in rec.notes

    def test_naive_filed_at_normalised_to_utc(self, tmp_path: Path):
        naive = datetime(2026, 5, 1, 12, 0, 0)
        record_filing(tmp_path, "C0001", filed_at=naive, channel="other")
        rec = get_filing(tmp_path, "C0001")
        assert rec is not None
        assert rec.filed_at.tzinfo is not None
        assert rec.filed_at.utcoffset() == timedelta(0)

    def test_filing_path_layout(self, tmp_path: Path):
        # Sidecar must live next to the case JSON for regulator-facing
        # bundle assembly.
        path = filing_path(tmp_path, "C0001")
        assert path.parent.name == "cases"
        assert path.name == "C0001__filing.json"

    def test_list_filings_empty_dir(self, tmp_path: Path):
        assert list_filings(tmp_path) == []

    def test_list_filings_returns_all_sorted(self, tmp_path: Path):
        for cid in ["C0003", "C0001", "C0002"]:
            record_filing(tmp_path, cid, filed_at=_AS_OF, channel="goaml")
        records = list_filings(tmp_path)
        assert [r.case_id for r in records] == ["C0001", "C0002", "C0003"]

    def test_corrupt_sidecar_skipped_in_list(self, tmp_path: Path):
        record_filing(tmp_path, "C0001", filed_at=_AS_OF, channel="goaml")
        # Drop a malformed file in the same dir.
        (tmp_path / "cases" / "C-CORRUPT__filing.json").write_text("not json", encoding="utf-8")
        records = list_filings(tmp_path)
        # Healthy sidecar surfaces; corrupt one is silently dropped.
        assert [r.case_id for r in records] == ["C0001"]


# ---------------------------------------------------------------------------
# filing_latency_days math
# ---------------------------------------------------------------------------


class TestFilingLatencyMath:
    def test_one_day_latency(self):
        opened = _AS_OF
        rec = FilingRecord(
            case_id="C0001",
            filed_at=_AS_OF + timedelta(days=1),
            channel="goaml",
        )
        assert filing_latency_days(rec, opened) == 1.0

    def test_subday_latency(self):
        opened = _AS_OF
        rec = FilingRecord(
            case_id="C0001",
            filed_at=_AS_OF + timedelta(hours=12),
            channel="goaml",
        )
        assert filing_latency_days(rec, opened) == 0.5

    def test_negative_latency_clamped_to_zero(self):
        # Backdated entry — pin to 0 so p95 isn't poisoned.
        opened = _AS_OF
        rec = FilingRecord(
            case_id="C0001",
            filed_at=_AS_OF - timedelta(days=1),
            channel="goaml",
        )
        assert filing_latency_days(rec, opened) == 0.0

    def test_handles_naive_inputs(self):
        # Mixed tz-aware / tz-naive should not crash.
        opened = datetime(2026, 5, 1, 12, 0)
        rec = FilingRecord(
            case_id="C0001",
            filed_at=datetime(2026, 5, 3, 12, 0),
            channel="other",
        )
        assert filing_latency_days(rec, opened) == 2.0


# ---------------------------------------------------------------------------
# End-to-end: metrics engine reads sidecars
# ---------------------------------------------------------------------------


class TestFilingLatencyMetric:
    def test_metric_uses_sidecar_when_present(self, tmp_path: Path):
        from aml_framework.data.synthetic import generate_dataset
        from aml_framework.engine.runner import run_spec
        from aml_framework.spec.loader import load_spec

        src = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(src)
        data = generate_dataset(as_of=_AS_OF, seed=42)

        # First run: no sidecars.
        result = run_spec(
            spec=spec,
            spec_path=src,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        # Find the filing-latency metric in the result.
        baseline_value = next(
            m.value
            for m in result.metrics
            if "filing" in m.id.lower() or "latency" in m.name.lower()
        )

        # Now record filings for two cases with a known latency, then
        # re-evaluate metrics from the same run dir. The metric should
        # reflect the real latencies (the run dir's case_opened
        # decisions have ts == as_of; we file 5 and 10 days later).
        if not result.case_ids:
            return  # unlikely — community_bank produces alerts
        record_filing(
            run_dir,
            result.case_ids[0],
            filed_at=_AS_OF + timedelta(days=5),
            channel="bsa_e_filing",
        )
        record_filing(
            run_dir,
            result.case_ids[1] if len(result.case_ids) > 1 else result.case_ids[0],
            filed_at=_AS_OF + timedelta(days=10),
            channel="bsa_e_filing",
        )

        # Re-evaluate metrics with run_dir set so sidecars are read.
        from aml_framework.metrics.engine import evaluate_metrics

        decisions_path = run_dir / "decisions.jsonl"
        decisions_rows = [
            json.loads(line)
            for line in decisions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cases_dir = run_dir / "cases"
        cases_rows = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(cases_dir.glob("*.json"))
            if not p.name.endswith("__filing.json")
        ]

        new_metrics = evaluate_metrics(
            spec=spec,
            alerts={},
            cases=cases_rows,
            decisions=decisions_rows,
            data=data,
            run_dir=run_dir,
        )
        new_value = next(
            m.value for m in new_metrics if "filing" in m.id.lower() or "latency" in m.name.lower()
        )
        # Real latency is 10 days at p95 (or 5 if only one filing was
        # recorded due to dedup of case_ids[0]==case_ids[1]).
        assert new_value in (5.0, 10.0), (
            f"expected real-latency value 5 or 10, got {new_value} (baseline was {baseline_value})"
        )

    def test_metric_falls_back_to_proxy_without_sidecars(self, tmp_path: Path):
        # No sidecars written — _proxy_filing_latency stays usable.
        from aml_framework.data.synthetic import generate_dataset
        from aml_framework.engine.runner import run_spec
        from aml_framework.spec.loader import load_spec

        src = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(src)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=src,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        # Some metric in the result should match the filing-latency
        # category; just assert it returned a number, not crashed.
        latency_metric = next(
            (m for m in result.metrics if "filing" in m.id.lower() or "latency" in m.name.lower()),
            None,
        )
        assert latency_metric is not None
        assert isinstance(latency_metric.value, (int, float))
