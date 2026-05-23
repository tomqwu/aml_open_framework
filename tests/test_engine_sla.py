"""PR-LF1 (#383) — Pillar-6 SLA-breach + batch-lateness monitor.

Covers:
- Pure evaluator (`evaluate_sla`) for the four shape cases:
  happy path / alert-breach only / batch-late only / both.
- Disabled-monitor path (no `program.sla` block) emits an empty report.
- JSON-schema accept/reject for the new `program.sla` field.
- Pydantic round-trip for the `ProgramSLA` model.
- The runner emits `sla_report.json` to the run dir.
- The artifact is in `_FROZEN_SNAPSHOT_TARGETS` (post-finalize integrity).
- `compute_spec_diff` surfaces sla changes per-attribute.
"""

from __future__ import annotations

import json
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.constants import Event
from aml_framework.engine.runner import run_spec
from aml_framework.engine.sla import (
    AlertSLABreach,
    SLAReport,
    evaluate_sla,
)
from aml_framework.spec.loader import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    ProgramSLA,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _txn_contract() -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
    )


def _default_rule() -> Rule:
    return Rule(
        id="r1",
        name="R1",
        severity="high",
        regulation_refs=[RegulationRef(citation="x", description="x")],
        logic=AggregationWindowLogic(
            type="aggregation_window",
            source="txn",
            group_by=["customer_id"],
            window="7d",
            having={"count": {"gte": 5}},
        ),
        escalate_to="q1",
        evidence=[],
    )


def _make_spec(
    *,
    sla: ProgramSLA | None = None,
    rules: list[Rule] | None = None,
) -> AMLSpec:
    """Build a minimal spec. `rules=None` → one default agg rule;
    pass `rules=[]` to disable detection for runner-side artifact tests."""
    if rules is None:
        rules = [_default_rule()]
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
            sla=sla,
        ),
        data_contracts=[_txn_contract()],
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _decisions(
    *,
    opened: list[tuple[str, str, datetime]],
    terminal: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """Build a decisions-event stream from per-case (case_id, rule_id, ts) tuples
    plus an optional list of (case_id, terminal_event) closings."""
    events: list[dict] = []
    for case_id, rule_id, ts in opened:
        events.append(
            {
                "ts": ts.isoformat(),
                "event": Event.CASE_OPENED,
                "case_id": case_id,
                "rule_id": rule_id,
            }
        )
    for case_id, kind in terminal or []:
        events.append(
            {
                "ts": _AS_OF.isoformat(),
                "event": kind,
                "case_id": case_id,
            }
        )
    return events


# ---------------------------------------------------------------------------
# Pure evaluator
# ---------------------------------------------------------------------------


class TestEvaluateSLAPure:
    def test_no_sla_block_returns_disabled_report(self):
        """Backward-compat: specs without `program.sla` get a disabled
        report. Artifact still has stable shape so dashboards don't crash."""
        spec = _make_spec(sla=None)
        report = evaluate_sla(spec, decisions=[], data={}, as_of=_AS_OF)
        assert isinstance(report, SLAReport)
        assert report.enabled is False
        assert report.total_breaches == 0
        assert report.breaches == []
        assert report.batch_late is False
        assert report.batch_lateness_days == 0
        assert report.latest_transaction_at is None

    def test_happy_path_no_breaches(self):
        """SLA declared, all open cases within budget, batch on time."""
        spec = _make_spec(
            sla=ProgramSLA(
                alert_disposition_days=30,
                batch_cadence_days=1,
                batch_lateness_grace_days=1,
            )
        )
        # case opened 5 days ago → well within 30d budget
        decisions = _decisions(opened=[("c1", "r1", _AS_OF - timedelta(days=5))])
        # transaction from yesterday → within 1d cadence + 1d grace
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=1)}]}
        report = evaluate_sla(spec, decisions, data, _AS_OF)
        assert report.enabled is True
        assert report.alert_disposition_days == 30
        assert report.total_breaches == 0
        assert report.breaches == []
        assert report.batch_late is False
        assert report.batch_lateness_days == 1
        assert report.latest_transaction_at is not None

    def test_alert_breach_only(self):
        """Case open older than threshold and never resolved → breach."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=10))
        decisions = _decisions(
            opened=[
                ("old_open", "r1", _AS_OF - timedelta(days=20)),
                ("fresh_open", "r1", _AS_OF - timedelta(days=2)),
                ("old_closed", "r1", _AS_OF - timedelta(days=20)),
            ],
            terminal=[("old_closed", Event.CLOSED)],
        )
        # batch on time so we isolate the alert-breach signal
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=1)}]}
        report = evaluate_sla(spec, decisions, data, _AS_OF)
        assert report.total_breaches == 1
        assert report.breaches[0].case_id == "old_open"
        assert report.breaches[0].rule_id == "r1"
        assert report.breaches[0].age_days == 20
        assert report.breaches_by_rule == {"r1": 1}
        assert report.batch_late is False

    def test_terminal_str_filing_clears_breach(self):
        """`escalated_to_str` is also terminal — filed alerts shouldn't
        count as in-flight."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=10))
        decisions = _decisions(
            opened=[("filed", "r1", _AS_OF - timedelta(days=30))],
            terminal=[("filed", Event.ESCALATED_TO_STR)],
        )
        report = evaluate_sla(spec, decisions, {}, _AS_OF)
        assert report.total_breaches == 0

    def test_batch_late_only(self):
        """Most recent txn is 5 days old vs cadence 1 + grace 1 = 2d
        budget → 5d > 2d, batch flagged late."""
        spec = _make_spec(
            sla=ProgramSLA(
                alert_disposition_days=30,
                batch_cadence_days=1,
                batch_lateness_grace_days=1,
            )
        )
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=5)}]}
        report = evaluate_sla(spec, decisions=[], data=data, as_of=_AS_OF)
        assert report.batch_late is True
        assert report.batch_lateness_days == 5
        assert report.total_breaches == 0

    def test_both_breaches_together(self):
        """Both signals fire on the same run — independent surfaces."""
        spec = _make_spec(
            sla=ProgramSLA(
                alert_disposition_days=10,
                batch_cadence_days=1,
                batch_lateness_grace_days=1,
            )
        )
        decisions = _decisions(
            opened=[
                ("alpha", "r1", _AS_OF - timedelta(days=15)),
                ("beta", "r2", _AS_OF - timedelta(days=25)),
            ]
        )
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=4)}]}
        report = evaluate_sla(spec, decisions, data, _AS_OF)
        assert report.total_breaches == 2
        assert report.breaches_by_rule == {"r1": 1, "r2": 1}
        # ordering: oldest breach first
        assert [b.case_id for b in report.breaches] == ["beta", "alpha"]
        assert report.batch_late is True
        assert report.batch_lateness_days == 4

    def test_lateness_at_exact_budget_not_flagged(self):
        """Boundary: gap == cadence + grace (no sub-day overshoot) must
        NOT trip lateness. Only `elapsed > budget_td` flags — the
        strictly-later semantics carry through the full-timedelta
        comparison (codex P2 pass-2)."""
        spec = _make_spec(sla=ProgramSLA(batch_cadence_days=1, batch_lateness_grace_days=1))
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=2)}]}
        report = evaluate_sla(spec, [], data, _AS_OF)
        assert report.batch_late is False
        assert report.batch_lateness_days == 2

    def test_sub_day_overshoot_flags_alert_breach(self):
        """Codex P2 pass-2: a case 10 days + 1 hour old with threshold
        `alert_disposition_days=10` must flag — `.days` would have floored
        the gap to 10 and `10 > 10` is False, suppressing the breach."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=10))
        decisions = _decisions(opened=[("c1", "r1", _AS_OF - timedelta(days=10, hours=1))])
        report = evaluate_sla(spec, decisions, {}, _AS_OF)
        assert report.total_breaches == 1
        assert report.breaches[0].age_days == 10  # floored display

    def test_sub_day_overshoot_flags_batch_late(self):
        """Codex P2 pass-2: a batch 2 days + 1 hour stale with budget=2d
        must flag — floored `.days` would suppress."""
        spec = _make_spec(sla=ProgramSLA(batch_cadence_days=1, batch_lateness_grace_days=1))
        data = {"txn": [{"booked_at": _AS_OF - timedelta(days=2, hours=1)}]}
        report = evaluate_sla(spec, [], data, _AS_OF)
        assert report.batch_late is True
        assert report.batch_lateness_days == 2  # floored display

    def test_age_at_exact_threshold_not_flagged(self):
        """Boundary on alert age — `age > threshold` flags. Day-equal stays
        in budget."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=10))
        decisions = _decisions(opened=[("c1", "r1", _AS_OF - timedelta(days=10))])
        report = evaluate_sla(spec, decisions, {}, _AS_OF)
        assert report.total_breaches == 0

    def test_no_transactions_no_lateness_signal(self):
        """Customer-only fixtures (no txn timestamp column) shouldn't
        synthesise a lateness signal — `latest_transaction_at` stays None."""
        spec = _make_spec(sla=ProgramSLA())
        report = evaluate_sla(spec, [], data={"customer": [{"customer_id": "C0001"}]}, as_of=_AS_OF)
        assert report.latest_transaction_at is None
        assert report.batch_late is False
        assert report.batch_lateness_days == 0

    def test_malformed_event_ts_is_skipped(self):
        """A `case_opened` event with an unparseable `ts` is skipped
        (mirrors freshness scanner's tolerant posture)."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=1))
        decisions = [
            {"event": Event.CASE_OPENED, "case_id": "bad", "rule_id": "r1", "ts": "not-a-date"},
            {
                "event": Event.CASE_OPENED,
                "case_id": "good",
                "rule_id": "r1",
                "ts": (_AS_OF - timedelta(days=5)).isoformat(),
            },
        ]
        report = evaluate_sla(spec, decisions, {}, _AS_OF)
        assert {b.case_id for b in report.breaches} == {"good"}

    def test_date_value_coerces_to_utc_midnight(self):
        """A bare `date` (not `datetime`) row value still latches as a
        latest-txn signal — loaders that hand back `date` shouldn't break
        the lateness calc."""
        spec = _make_spec(sla=ProgramSLA(batch_cadence_days=1, batch_lateness_grace_days=1))
        latest = _AS_OF.date()  # bare date
        data = {"txn": [{"booked_at": latest}]}
        report = evaluate_sla(spec, [], data, _AS_OF)
        # `date` parsed as UTC midnight; same day as `as_of` (also UTC) →
        # batch_lateness_days could be 0 or 1 depending on the time-of-day
        # in `_AS_OF`. We only assert the signal *latched* (latest_ts set).
        assert report.latest_transaction_at is not None

    def test_row_with_null_or_missing_txn_timestamp_skipped(self):
        """Rows whose `booked_at` is None (sparse fixture) don't crash
        the scanner; the row is just skipped."""
        spec = _make_spec(sla=ProgramSLA())
        data = {
            "txn": [
                {"booked_at": None},
                {"booked_at": "not-a-timestamp"},
                {"booked_at": _AS_OF - timedelta(days=1)},
            ]
        }
        report = evaluate_sla(spec, [], data, _AS_OF)
        # only the well-formed row latches
        assert report.latest_transaction_at is not None

    def test_event_without_case_id_is_skipped(self):
        """Decision events that aren't case-scoped (e.g. dq_exception,
        contract_violation) don't have a `case_id`; the evaluator must
        ignore them rather than counting them as opens or terminals."""
        spec = _make_spec(sla=ProgramSLA(alert_disposition_days=10))
        decisions = [
            {"event": Event.DQ_EXCEPTION, "ts": _AS_OF.isoformat()},
            {
                "event": Event.CASE_OPENED,
                "case_id": "c1",
                "rule_id": "r1",
                "ts": (_AS_OF - timedelta(days=20)).isoformat(),
            },
        ]
        report = evaluate_sla(spec, decisions, {}, _AS_OF)
        assert report.total_breaches == 1


# ---------------------------------------------------------------------------
# Spec / schema round-trip
# ---------------------------------------------------------------------------


class TestProgramSLASpec:
    def test_default_is_none(self):
        """Existing specs without `sla` keep loading — additive contract."""
        spec = load_spec(EXAMPLE)
        assert spec.program.sla is None

    def test_full_block_round_trips(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["sla"] = {
            "alert_disposition_days": 14,
            "batch_cadence_days": 1,
            "batch_lateness_grace_days": 2,
        }
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.sla is not None
        sla = spec.program.sla
        assert sla.alert_disposition_days == 14
        assert sla.batch_cadence_days == 1
        assert sla.batch_lateness_grace_days == 2

    def test_partial_block_uses_defaults(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["sla"] = {"alert_disposition_days": 7}
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.sla is not None
        assert spec.program.sla.alert_disposition_days == 7
        # Defaults
        assert spec.program.sla.batch_cadence_days == 1
        assert spec.program.sla.batch_lateness_grace_days == 1

    def test_negative_value_rejected(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["sla"] = {"alert_disposition_days": -1}
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)

    def test_unknown_field_rejected(self, tmp_path):
        """`additionalProperties: false` + `extra="forbid"` — typos must
        not silently slip past validation."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["sla"] = {"disposition_days": 30}  # typo
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)

    def test_pydantic_model_round_trips(self):
        sla = ProgramSLA(
            alert_disposition_days=21,
            batch_cadence_days=7,
            batch_lateness_grace_days=2,
        )
        dumped = sla.model_dump()
        restored = ProgramSLA(**dumped)
        assert restored == sla

    def test_pydantic_model_defaults(self):
        sla = ProgramSLA()
        assert sla.alert_disposition_days == 30
        assert sla.batch_cadence_days == 1
        assert sla.batch_lateness_grace_days == 1


# ---------------------------------------------------------------------------
# Runner artifact
# ---------------------------------------------------------------------------


class TestRunnerEmitsSLAReport:
    @staticmethod
    def _spec_path(spec: AMLSpec, tmp_path: Path) -> Path:
        """Persist a minimal YAML for `spec_content_hash` to read."""
        path = tmp_path / "spec.yaml"
        path.write_text(yaml.safe_dump(spec.model_dump(mode="json")))
        return path

    def test_sla_report_artifact_always_present(self, tmp_path):
        """Runner emits `sla_report.json` even when `program.sla` is unset.
        Mirrors the artifact-always-present invariant from dq_exceptions
        + field_lineage."""
        # Empty rules list keeps the warehouse build trivial and avoids
        # firing detection logic — we're only asserting the SLA artifact
        # is always written.
        spec = _make_spec(sla=None, rules=[])
        result = run_spec(
            spec=spec,
            spec_path=self._spec_path(spec, tmp_path),
            data={"txn": []},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        sla_path = Path(result.manifest["run_dir"]) / "sla_report.json"
        assert sla_path.exists()
        body = json.loads(sla_path.read_bytes())
        assert body["enabled"] is False
        assert body["total_breaches"] == 0

    def test_sla_report_artifact_populated_when_enabled(self, tmp_path):
        """With `program.sla` declared and a stale-batch fixture, the run
        emits a populated report (batch_late = True)."""
        spec = _make_spec(
            sla=ProgramSLA(
                alert_disposition_days=30,
                batch_cadence_days=1,
                batch_lateness_grace_days=1,
            ),
            rules=[],
        )
        # 10 transactions all older than the lateness budget so the
        # evaluator picks up the latest-timestamp signal.
        old_ts = _AS_OF - timedelta(days=10)
        rows = [
            {
                "txn_id": f"T{i}",
                "customer_id": f"C{i:04d}",
                "amount": 100.0,
                "booked_at": old_ts,
            }
            for i in range(3)
        ]
        result = run_spec(
            spec=spec,
            spec_path=self._spec_path(spec, tmp_path),
            data={"txn": rows},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        sla_path = Path(result.manifest["run_dir"]) / "sla_report.json"
        body = json.loads(sla_path.read_bytes())
        assert body["enabled"] is True
        assert body["alert_disposition_days"] == 30
        assert body["batch_late"] is True
        assert body["batch_lateness_days"] == 10

    def test_manifest_pins_sla_report_hash(self, tmp_path):
        """Codex P2 on PR-LF1: the manifest must carry a SHA-256 of
        `sla_report.json` so post-finalize edits are detectable on
        Windows (chmod 0o444 is a no-op there) or any environment
        where the freeze can be undone."""
        import hashlib

        spec = _make_spec(sla=ProgramSLA(), rules=[])
        result = run_spec(
            spec=spec,
            spec_path=self._spec_path(spec, tmp_path),
            data={"txn": []},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        run_dir = Path(result.manifest["run_dir"])
        sla_bytes = (run_dir / "sla_report.json").read_bytes()
        expected = hashlib.sha256(sla_bytes).hexdigest()
        assert result.manifest["sla_report_hash"] == expected, (
            "manifest must pin SHA-256 of sla_report.json for tamper detection"
        )

    def test_coerce_datetime_accepts_z_suffix(self):
        """Codex P2 on PR-LF1: `datetime.fromisoformat` on Python 3.10
        rejects the `Z` UTC suffix; the evaluator must normalise so that
        warehouse exports / JSON ingest with `...Z` timestamps don't
        silently get skipped."""
        spec = _make_spec(sla=ProgramSLA(batch_cadence_days=1, batch_lateness_grace_days=1))
        # Stale txn supplied as an ISO 8601 string with Z suffix.
        stale_iso = (_AS_OF - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = {"txn": [{"booked_at": stale_iso}]}
        report = evaluate_sla(spec, [], data, _AS_OF)
        # If `Z` were silently dropped, `latest_transaction_at` would be
        # None and batch_late would be False — the assertion below would
        # fail. With normalisation, the row latches and batch is late.
        assert report.latest_transaction_at is not None
        assert report.batch_late is True
        assert report.batch_lateness_days == 10

    def test_sla_report_in_frozen_targets(self):
        """Audit-integrity posture: the artifact must be in the frozen
        list so a post-finalize chmod 0o444 lands on it."""
        assert "sla_report.json" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# Spec diff
# ---------------------------------------------------------------------------


class TestSpecDiffSurfacesSLA:
    def test_sla_only_change_surfaces_as_program_change(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "program": {**raw["program"], "sla": {"alert_disposition_days": 30}}}
        raw_b = {**raw, "program": {**raw["program"], "sla": {"alert_disposition_days": 15}}}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        sla_changes = [c for c in result.program_changes if c.field.startswith("sla.")]
        assert any(
            c.field == "sla.alert_disposition_days" and c.before == "30" and c.after == "15"
            for c in sla_changes
        ), f"expected sla.alert_disposition_days 30→15; got {sla_changes}"

    def test_adding_sla_block_surfaces_in_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_b = {
            **raw,
            "program": {**raw["program"], "sla": {"alert_disposition_days": 14}},
        }
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        sla_changes = [c for c in result.program_changes if c.field.startswith("sla.")]
        assert any(
            c.field == "sla.alert_disposition_days" and c.before == "" and c.after == "14"
            for c in sla_changes
        ), f"adding sla block must surface; got {sla_changes}"


# ---------------------------------------------------------------------------
# AlertSLABreach model — verify shape
# ---------------------------------------------------------------------------


class TestAlertSLABreachModel:
    def test_round_trip(self):
        b = AlertSLABreach(
            case_id="c1",
            rule_id="r1",
            opened_at=_AS_OF,
            age_days=42,
        )
        restored = AlertSLABreach(**b.model_dump())
        assert restored == b
