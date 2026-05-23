"""Post-run monitoring digest (PR-LF4 — issue #386).

Covers:
- Pydantic model invariants (frozen + extra="forbid")
- Pure aggregation: alerts per rule, per queue, per severity
- Top-3 ranking with tie-break on rule_id
- DQ rollup by check_type and contract_id
- "Changed since last run" diff against a prior manifest
- Empty / missing prior run → empty diff dict
- Engine integration: monitoring_digest.json artifact written
- Manifest pins monitoring_digest_hash for tamper detection
- Artifact membership in _FROZEN_SNAPSHOT_TARGETS
- Byte-stable JSON output (sort_keys=True)
- Graceful degradation when api.db is unavailable
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.dq import DQException
from aml_framework.engine.monitoring_digest import (
    MonitoringDigest,
    RuleAlertCount,
    _diff_against_prior,
    _top_rules,
    build_monitoring_digest,
    lookup_prior_run,
    write_monitoring_digest,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)


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


def _make_rule(
    rule_id: str,
    *,
    severity: str = "low",
    escalate_to: str = "q1",
) -> Rule:
    return Rule(
        id=rule_id,
        name=rule_id.upper(),
        severity=severity,
        regulation_refs=[RegulationRef(citation="x", description="x")],
        logic=AggregationWindowLogic(
            type="aggregation_window",
            source="txn",
            group_by=["customer_id"],
            window="365d",
            having={"count": {"gte": 1}},
        ),
        escalate_to=escalate_to,
        evidence=[],
    )


def _make_spec(*, rules: list[Rule] | None = None, queues: list[Queue] | None = None) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="TestProgram",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=[_txn_contract()],
        rules=rules if rules is not None else [_make_rule("r1")],
        workflow=Workflow(
            queues=queues if queues is not None else [Queue(id="q1", sla="24h")],
        ),
    )


# ---------------------------------------------------------------------------
# Pydantic model invariants
# ---------------------------------------------------------------------------


class TestMonitoringDigestModel:
    def _digest_kwargs(self) -> dict:
        return dict(
            spec_name="T",
            spec_path="/tmp/spec.yaml",
            spec_content_hash="abc",
            as_of=_AS_OF,
            engine_version="0.0.0",
            run_dir="/tmp/run-x",
            total_alerts=0,
            alerts_per_rule={},
            alerts_per_queue={},
            alerts_per_severity={},
            top_rules=[],
            dq_total=0,
            dq_per_check_type={},
            dq_per_contract={},
            prior_run_id=None,
            changed_since_last_run={},
        )

    def test_digest_is_frozen(self):
        d = MonitoringDigest(**self._digest_kwargs())
        with pytest.raises(Exception):
            d.total_alerts = 5  # type: ignore[misc]

    def test_digest_forbids_extra_fields(self):
        kwargs = self._digest_kwargs()
        kwargs["surprise"] = 1
        with pytest.raises(Exception):
            MonitoringDigest(**kwargs)  # type: ignore[arg-type]

    def test_rule_alert_count_is_frozen(self):
        r = RuleAlertCount(rule_id="r1", count=3)
        with pytest.raises(Exception):
            r.count = 99  # type: ignore[misc]

    def test_rule_alert_count_forbids_extra_fields(self):
        with pytest.raises(Exception):
            RuleAlertCount(rule_id="r1", count=3, junk=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Pure aggregation
# ---------------------------------------------------------------------------


class TestBuildMonitoringDigest:
    def test_happy_path_rolls_up_alerts(self, tmp_path: Path):
        rules = [
            _make_rule("r_high", severity="high", escalate_to="q_high"),
            _make_rule("r_low", severity="low", escalate_to="q_low"),
        ]
        spec = _make_spec(
            rules=rules,
            queues=[Queue(id="q_high", sla="24h"), Queue(id="q_low", sla="72h")],
        )
        alerts = {
            "r_high": [{"customer_id": "C1"}, {"customer_id": "C2"}],
            "r_low": [{"customer_id": "C3"}],
        }
        digest = build_monitoring_digest(
            spec,
            run_dir=tmp_path,
            spec_path=Path("/tmp/spec.yaml"),
            spec_content_hash="abc",
            engine_version="0.1.0",
            as_of=_AS_OF,
            alerts_by_rule=alerts,
            dq_exceptions=[],
            prior_run=None,
        )
        assert digest.total_alerts == 3
        assert digest.alerts_per_rule == {"r_high": 2, "r_low": 1}
        assert digest.alerts_per_queue == {"q_high": 2, "q_low": 1}
        assert digest.alerts_per_severity == {"high": 2, "low": 1}
        assert digest.spec_name == "TestProgram"

    def test_top_rules_ranks_descending_with_tie_break(self):
        # Two rules tied at 3 alerts — alphabetical rule_id breaks the tie.
        out = _top_rules({"b": 3, "a": 3, "c": 5, "d": 0})
        assert [(r.rule_id, r.count) for r in out] == [("c", 5), ("a", 3), ("b", 3)]

    def test_top_rules_excludes_zero_count_rules(self):
        out = _top_rules({"a": 0, "b": 0, "c": 1})
        assert len(out) == 1
        assert out[0].rule_id == "c"

    def test_top_rules_caps_at_three_by_default(self):
        counts = {f"r{i}": i for i in range(1, 10)}
        out = _top_rules(counts)
        assert len(out) == 3
        assert [r.rule_id for r in out] == ["r9", "r8", "r7"]

    def test_dq_rollup_by_check_type_and_contract(self, tmp_path: Path):
        spec = _make_spec()
        excs = [
            DQException(
                contract_id="txn",
                check_id="not_null:amount",
                check_type="not_null",
                column="amount",
                reason="null",
                row_index=0,
            ),
            DQException(
                contract_id="txn",
                check_id="not_null:amount",
                check_type="not_null",
                column="amount",
                reason="null",
                row_index=2,
            ),
            DQException(
                contract_id="txn",
                check_id="unique:txn_id",
                check_type="unique",
                column="txn_id",
                reason="dup",
                failing_value="T1",
            ),
        ]
        digest = build_monitoring_digest(
            spec,
            run_dir=tmp_path,
            spec_path=Path("/tmp/s.yaml"),
            spec_content_hash="h",
            engine_version="0",
            as_of=_AS_OF,
            alerts_by_rule={},
            dq_exceptions=excs,
            prior_run=None,
        )
        assert digest.dq_total == 3
        assert digest.dq_per_check_type == {"not_null": 2, "unique": 1}
        assert digest.dq_per_contract == {"txn": 3}

    def test_no_prior_run_yields_empty_diff(self, tmp_path: Path):
        spec = _make_spec()
        digest = build_monitoring_digest(
            spec,
            run_dir=tmp_path,
            spec_path=Path("/tmp/s.yaml"),
            spec_content_hash="h",
            engine_version="0",
            as_of=_AS_OF,
            alerts_by_rule={"r1": [{"customer_id": "C1"}]},
            dq_exceptions=[],
            prior_run=None,
        )
        assert digest.prior_run_id is None
        assert digest.changed_since_last_run == {}


# ---------------------------------------------------------------------------
# Prior-run diff
# ---------------------------------------------------------------------------


class TestDiffAgainstPrior:
    def test_diff_with_explicit_prior_counts(self):
        prior = {
            "run_id": "run-prior",
            "monitoring_digest": {"alerts_per_rule": {"r1": 5, "r2": 1}},
        }
        run_id, delta = _diff_against_prior({"r1": 3, "r2": 4, "r3": 2}, prior)
        assert run_id == "run-prior"
        # Diff for every rule_id touched in either side.
        assert delta == {"r1": -2, "r2": 3, "r3": 2}

    def test_diff_falls_back_to_rule_outputs_when_no_digest_block(self):
        # Older runs predating PR-LF4 won't carry monitoring_digest;
        # fall back to rule_outputs (hash strings — treated as zero
        # baseline so the diff still surfaces).
        prior = {
            "run_id": "run-old",
            "rule_outputs": {"r1": "deadbeef", "r2": "cafef00d"},
        }
        run_id, delta = _diff_against_prior({"r1": 4}, prior)
        assert run_id == "run-old"
        # r1 grew by 4 (4 - 0 baseline); r2 was present in prior but
        # absent now → -0 (since we have no count baseline) = 0.
        assert delta == {"r1": 4, "r2": 0}

    def test_diff_uses_run_dir_when_run_id_missing(self):
        prior = {"run_dir": "/tmp/run-xyz", "monitoring_digest": {"alerts_per_rule": {"r1": 1}}}
        run_id, _ = _diff_against_prior({"r1": 2}, prior)
        assert run_id == "/tmp/run-xyz"

    def test_diff_returns_empty_when_prior_is_none(self):
        assert _diff_against_prior({"r1": 5}, None) == (None, {})

    def test_diff_returns_empty_when_prior_is_empty_dict(self):
        assert _diff_against_prior({"r1": 5}, {}) == (None, {})

    def test_diff_handles_malformed_digest_block(self):
        # Defensive: digest block exists but isn't a dict.
        prior = {"run_id": "rx", "monitoring_digest": "not-a-dict"}
        run_id, delta = _diff_against_prior({"r1": 2}, prior)
        assert run_id == "rx"
        assert delta == {"r1": 2}

    def test_diff_handles_malformed_alerts_per_rule(self):
        # digest block exists but alerts_per_rule isn't a dict.
        prior = {"run_id": "rx", "monitoring_digest": {"alerts_per_rule": "nope"}}
        run_id, delta = _diff_against_prior({"r1": 2}, prior)
        assert run_id == "rx"
        assert delta == {"r1": 2}

    def test_diff_handles_non_string_run_id(self):
        prior = {"run_id": 12345, "monitoring_digest": {"alerts_per_rule": {"r1": 1}}}
        run_id, _ = _diff_against_prior({"r1": 2}, prior)
        # Non-string run_id → falls through to run_dir (not set) → None.
        assert run_id is None


# ---------------------------------------------------------------------------
# Prior-run lookup graceful degradation
# ---------------------------------------------------------------------------


class TestLookupPriorRun:
    def test_returns_none_when_no_runs_listed(self):
        with patch("aml_framework.api.db.list_runs", return_value=[]):
            assert lookup_prior_run("/tmp/spec.yaml") is None

    def test_returns_none_when_list_runs_raises(self):
        with patch("aml_framework.api.db.list_runs", side_effect=RuntimeError("db down")):
            assert lookup_prior_run("/tmp/spec.yaml") is None

    def test_returns_none_when_get_run_raises(self):
        runs = [{"run_id": "rx", "spec_path": "/tmp/spec.yaml"}]
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", side_effect=RuntimeError("boom")),
        ):
            assert lookup_prior_run("/tmp/spec.yaml") is None

    def test_returns_manifest_for_matching_spec(self):
        runs = [
            {"run_id": "ry", "spec_path": "/tmp/other.yaml"},
            {"run_id": "rx", "spec_path": "/tmp/spec.yaml"},
        ]
        manifest = {"rule_outputs": {"r1": "deadbeef"}}
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", return_value=manifest) as get_run,
        ):
            out = lookup_prior_run("/tmp/spec.yaml")
            get_run.assert_called_once_with("rx")
            assert out is not None
            assert out["run_id"] == "rx"

    def test_skips_current_run_dir(self):
        runs = [
            {"run_id": "/tmp/run-current", "spec_path": "/tmp/spec.yaml"},
            {"run_id": "/tmp/run-older", "spec_path": "/tmp/spec.yaml"},
        ]
        manifest = {"rule_outputs": {}}
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", return_value=manifest) as get_run,
        ):
            out = lookup_prior_run("/tmp/spec.yaml", current_run_dir="/tmp/run-current")
            get_run.assert_called_once_with("/tmp/run-older")
            assert out["run_id"] == "/tmp/run-older"

    def test_skips_runs_with_no_run_id(self):
        runs = [
            {"spec_path": "/tmp/spec.yaml"},  # no run_id
            {"run_id": "rx", "spec_path": "/tmp/spec.yaml"},
        ]
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", return_value={"k": "v"}) as get_run,
        ):
            out = lookup_prior_run("/tmp/spec.yaml")
            get_run.assert_called_once_with("rx")
            assert out is not None

    def test_skips_non_dict_runs(self):
        runs = ["not-a-dict", {"run_id": "rx", "spec_path": "/tmp/spec.yaml"}]
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", return_value={"k": "v"}),
        ):
            assert lookup_prior_run("/tmp/spec.yaml") is not None

    def test_returns_none_when_get_run_returns_non_dict(self):
        runs = [{"run_id": "rx", "spec_path": "/tmp/spec.yaml"}]
        with (
            patch("aml_framework.api.db.list_runs", return_value=runs),
            patch("aml_framework.api.db.get_run", return_value=None),
        ):
            assert lookup_prior_run("/tmp/spec.yaml") is None

    def test_returns_none_when_list_runs_returns_none(self):
        with patch("aml_framework.api.db.list_runs", return_value=None):
            assert lookup_prior_run("/tmp/spec.yaml") is None

    def test_returns_none_when_api_db_import_fails(self):
        """Persistence layer is optional. If `aml_framework.api.db`
        can't be imported (e.g. minimal install without the api extra),
        the prior-run lookup must degrade to None rather than crash.
        """
        import builtins
        import sys

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "aml_framework.api" or name.startswith("aml_framework.api."):
                raise ImportError("simulated missing api extra")
            return real_import(name, *args, **kwargs)

        # Remove any cached module entry so the import statement re-resolves.
        saved = {
            k: sys.modules.pop(k)
            for k in list(sys.modules)
            if k == "aml_framework.api" or k.startswith("aml_framework.api.")
        }
        try:
            with patch.object(builtins, "__import__", side_effect=fake_import):
                assert lookup_prior_run("/tmp/spec.yaml") is None
        finally:
            sys.modules.update(saved)


# ---------------------------------------------------------------------------
# Byte-stable write
# ---------------------------------------------------------------------------


class TestWriteMonitoringDigest:
    def _digest(self) -> MonitoringDigest:
        return MonitoringDigest(
            spec_name="T",
            spec_path="/tmp/s.yaml",
            spec_content_hash="h",
            as_of=_AS_OF,
            engine_version="0",
            run_dir="/tmp/run-x",
            total_alerts=2,
            alerts_per_rule={"a": 1, "b": 1},
            alerts_per_queue={"q1": 2},
            alerts_per_severity={"low": 2},
            top_rules=[RuleAlertCount(rule_id="a", count=1), RuleAlertCount(rule_id="b", count=1)],
            dq_total=0,
            dq_per_check_type={},
            dq_per_contract={},
            prior_run_id=None,
            changed_since_last_run={},
        )

    def test_write_produces_byte_stable_output(self, tmp_path: Path):
        d = self._digest()
        p1 = write_monitoring_digest(tmp_path, d)
        b1 = p1.read_bytes()
        p1.unlink()
        # Same digest written twice → identical bytes.
        p2 = write_monitoring_digest(tmp_path, d)
        assert p2.read_bytes() == b1

    def test_write_returns_path_to_artifact(self, tmp_path: Path):
        out = write_monitoring_digest(tmp_path, self._digest())
        assert out == tmp_path / "monitoring_digest.json"
        assert out.exists()

    def test_written_file_is_valid_json(self, tmp_path: Path):
        out = write_monitoring_digest(tmp_path, self._digest())
        parsed = json.loads(out.read_text(encoding="utf-8"))
        assert parsed["total_alerts"] == 2
        # sort_keys=True means top-level keys are alphabetical.
        keys = list(parsed.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


def _txn_data() -> dict:
    # Use timestamps strictly INSIDE the 365d window (not at the
    # `as_of` boundary). Python 3.12 + DuckDB treats boundary-equal
    # tz-aware timestamps differently than 3.14, so a row booked at
    # exactly `as_of` may be excluded by the window predicate on CI.
    inside_window = _AS_OF - timedelta(days=1)
    return {
        "txn": [
            {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": inside_window},
            {"txn_id": "T2", "customer_id": "C1", "amount": 20.0, "booked_at": inside_window},
        ],
    }


class TestRunSpecEmitsMonitoringDigest:
    def test_digest_artifact_is_written(self, tmp_path: Path):
        spec = _make_spec()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_txn_data(),
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        digest_path = run_dir / "monitoring_digest.json"
        assert digest_path.exists()
        parsed = json.loads(digest_path.read_text(encoding="utf-8"))
        assert parsed["spec_name"] == "TestProgram"
        assert parsed["total_alerts"] >= 1
        assert "r1" in parsed["alerts_per_rule"]

    def test_manifest_pins_monitoring_digest_hash(self, tmp_path: Path):
        spec = _make_spec()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_txn_data(),
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        digest_bytes = (run_dir / "monitoring_digest.json").read_bytes()
        expected = hashlib.sha256(digest_bytes).hexdigest()
        assert manifest["monitoring_digest_hash"] == expected

    def test_digest_artifact_in_frozen_targets(self):
        assert "monitoring_digest.json" in _FROZEN_SNAPSHOT_TARGETS

    def test_runner_continues_when_lookup_returns_none(self, tmp_path: Path):
        spec = _make_spec()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        # Patch the binding in the runner module — `lookup_prior_run` is
        # imported at module load, so patching the source module is a
        # no-op for the runner's call site.
        with patch(
            "aml_framework.engine.runner.lookup_prior_run",
            return_value=None,
        ):
            run_spec(
                spec=spec,
                spec_path=spec_path,
                data=_txn_data(),
                as_of=_AS_OF,
                artifacts_root=tmp_path,
            )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        parsed = json.loads((run_dir / "monitoring_digest.json").read_text(encoding="utf-8"))
        assert parsed["prior_run_id"] is None
        assert parsed["changed_since_last_run"] == {}

    def test_runner_records_diff_when_prior_exists(self, tmp_path: Path):
        spec = _make_spec()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        prior = {
            "run_id": "run-prior-xyz",
            "monitoring_digest": {"alerts_per_rule": {"r1": 0}},
        }
        with patch(
            "aml_framework.engine.runner.lookup_prior_run",
            return_value=prior,
        ):
            run_spec(
                spec=spec,
                spec_path=spec_path,
                data=_txn_data(),
                as_of=_AS_OF,
                artifacts_root=tmp_path,
            )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        parsed = json.loads((run_dir / "monitoring_digest.json").read_text(encoding="utf-8"))
        assert parsed["prior_run_id"] == "run-prior-xyz"
        # r1 fired in the current run vs zero in prior → positive delta.
        assert parsed["changed_since_last_run"]["r1"] >= 1
