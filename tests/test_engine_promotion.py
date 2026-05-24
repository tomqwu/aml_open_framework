"""PR-D3 (#376) — environment promotion model.

Covers:
- Pydantic models: `SignoffEvent`, `EnvironmentPromotion`,
  `Environment` literal accepted on `Program.environment` and
  `Rule.environments`.
- `is_rule_approved_for_environment` matrix across all 4 lanes
  (dev/test/uat/prod), including the default-fallback case.
- `promotion_audit_event` envelope: approved, warn-only, strict-block.
- Runner WARNs (logger) when a rule fires in an unapproved lane and
  raises `EnvironmentGatingError` when `strict_environment_gating=True`.
- Spec loader accepts the new program + rule fields; round-trip
  defaults stay backward-compatible.
- JSON schema accepts/rejects the new fields per the enum.
- Audit ledger records the gate-check event for every rule (approved
  AND blocked) so the regulator pack proves the gate was consulted.
- `compute_spec_diff` surfaces both program.environment changes and
  rule.environments changes.
"""

from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from aml_framework.engine.promotion import (
    EnvironmentGatingError,
    EnvironmentPromotion,
    SignoffEvent,
    is_rule_approved_for_environment,
    promotion_audit_event,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.loader import load_spec
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

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _sample_rows() -> list[dict]:
    """One row keeps the warehouse build non-empty so the agg rule
    compiles. Below the rule threshold (count >= 5) so the run produces
    no alerts — we exercise the gate hook, not the detection logic."""
    return [
        {
            "txn_id": "T1",
            "customer_id": "C0001",
            "amount": 100.0,
            "booked_at": _AS_OF,
        }
    ]


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


def _rule(rule_id: str = "r1", environments: list[str] | None = None) -> Rule:
    kwargs: dict = {}
    if environments is not None:
        kwargs["environments"] = environments
    return Rule(
        id=rule_id,
        name=rule_id.upper(),
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
        **kwargs,
    )


def _make_spec(
    *,
    environment: str = "dev",
    strict: bool = False,
    rule_environments: list[str] | None = None,
) -> AMLSpec:
    program_kwargs: dict = {
        "name": "T",
        "jurisdiction": "US",
        "regulator": "FinCEN",
        "owner": "MLRO",
        "effective_date": _date(2026, 1, 1),
        "environment": environment,
        "strict_environment_gating": strict,
    }
    return AMLSpec(
        version=1,
        program=Program(**program_kwargs),
        data_contracts=[_txn_contract()],
        rules=[_rule(environments=rule_environments)],
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _spec_path(spec: AMLSpec, tmp_path: Path) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json")))
    return path


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestProgramEnvironmentDefaults:
    def test_default_environment_is_dev(self):
        spec = load_spec(EXAMPLE)
        assert spec.program.environment == "dev"

    def test_default_strict_is_false(self):
        spec = load_spec(EXAMPLE)
        assert spec.program.strict_environment_gating is False

    def test_default_rule_environments_is_dev_only(self):
        spec = load_spec(EXAMPLE)
        for rule in spec.rules:
            assert rule.environments == ["dev"]

    def test_program_environment_accepts_all_four_lanes(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        for lane in ("dev", "test", "uat", "prod"):
            raw["program"]["environment"] = lane
            f = tmp_path / f"aml-{lane}.yaml"
            f.write_text(yaml.safe_dump(raw))
            spec = load_spec(f)
            assert spec.program.environment == lane

    def test_program_environment_rejects_bogus_lane(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["environment"] = "staging"  # not in the enum
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)

    def test_strict_gating_round_trips(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["strict_environment_gating"] = True
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.strict_environment_gating is True


class TestRuleEnvironments:
    def test_rule_environments_accepts_multiple_lanes(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["environments"] = ["dev", "test", "uat", "prod"]
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].environments == ["dev", "test", "uat", "prod"]

    def test_rule_environments_rejects_duplicates(self):
        with pytest.raises(ValueError):
            _rule(environments=["dev", "dev"])

    def test_rule_environments_rejects_unknown_lane(self):
        with pytest.raises(ValueError):
            _rule(environments=["prod", "qa"])  # qa is not a lane

    def test_rule_pending_promotion_status_loads(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["status"] = "pending_promotion"
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].status == "pending_promotion"


class TestSignoffAndPromotionModels:
    def test_signoff_event_round_trips(self):
        ev = SignoffEvent(
            rule_id="r1",
            environment="prod",
            signed_off_by="mlro@bank.com",
            signed_off_at=_AS_OF,
            note="Quarterly promotion review.",
        )
        dumped = ev.model_dump()
        restored = SignoffEvent(**dumped)
        assert restored == ev

    def test_environment_promotion_round_trips(self):
        ev = SignoffEvent(
            rule_id="r1",
            environment="test",
            signed_off_by="qa@bank.com",
            signed_off_at=_AS_OF,
        )
        promo = EnvironmentPromotion(
            rule_id="r1",
            current_environment="test",
            approved_environments=["dev", "test"],
            signoffs=[ev],
        )
        dumped = promo.model_dump()
        restored = EnvironmentPromotion(**dumped)
        assert restored == promo
        assert restored.signoffs[0].signed_off_by == "qa@bank.com"

    def test_signoff_event_is_frozen(self):
        ev = SignoffEvent(
            rule_id="r1",
            environment="dev",
            signed_off_by="x",
            signed_off_at=_AS_OF,
        )
        with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
            ev.note = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pure approval check
# ---------------------------------------------------------------------------


class TestIsRuleApprovedForEnvironment:
    @pytest.mark.parametrize(
        ("rule_envs", "program_env", "expected"),
        [
            (["dev"], "dev", True),
            (["dev"], "test", False),
            (["dev"], "uat", False),
            (["dev"], "prod", False),
            (["dev", "test"], "test", True),
            (["dev", "test"], "uat", False),
            (["dev", "test", "uat"], "uat", True),
            (["dev", "test", "uat", "prod"], "prod", True),
            (["prod"], "dev", False),  # cleared straight to prod
            (["uat", "prod"], "test", False),
        ],
    )
    def test_matrix(self, rule_envs, program_env, expected):
        rule = _rule(environments=rule_envs)
        spec = _make_spec(environment=program_env, rule_environments=rule_envs)
        assert is_rule_approved_for_environment(rule, spec.program) is expected


# ---------------------------------------------------------------------------
# Audit event envelope
# ---------------------------------------------------------------------------


class TestPromotionAuditEvent:
    def test_approved_event_shape(self):
        spec = _make_spec(environment="dev", rule_environments=["dev"])
        rule = spec.rules[0]
        event = promotion_audit_event(rule, spec.program, approved=True)
        assert event["event"] == "environment_gate_check"
        assert event["rule_id"] == "r1"
        assert event["program_environment"] == "dev"
        assert event["approved_environments"] == ["dev"]
        assert event["approved"] is True
        assert event["strict"] is False
        assert event["outcome"] == "approved"

    def test_blocked_event_when_strict(self):
        spec = _make_spec(environment="prod", strict=True, rule_environments=["dev"])
        rule = spec.rules[0]
        event = promotion_audit_event(rule, spec.program, approved=False)
        assert event["approved"] is False
        assert event["strict"] is True
        assert event["outcome"] == "blocked"

    def test_warn_only_event_when_not_strict(self):
        spec = _make_spec(environment="prod", strict=False, rule_environments=["dev"])
        rule = spec.rules[0]
        event = promotion_audit_event(rule, spec.program, approved=False)
        assert event["approved"] is False
        assert event["strict"] is False
        assert event["outcome"] == "warn_only"

    def test_strict_override_param(self):
        """`strict=` kwarg overrides the program's flag — useful for
        tests / what-if simulations that don't want to mutate the spec."""
        spec = _make_spec(environment="prod", strict=False, rule_environments=["dev"])
        rule = spec.rules[0]
        event = promotion_audit_event(rule, spec.program, approved=False, strict=True)
        assert event["strict"] is True
        assert event["outcome"] == "blocked"


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


class TestRunnerGate:
    def test_approved_rule_runs_without_warning(self, tmp_path, caplog):
        spec = _make_spec(environment="prod", rule_environments=["dev", "prod"])
        with caplog.at_level(logging.WARNING, logger="aml.engine.runner"):
            run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        # No "is only approved for" warning emitted.
        assert not any("is only approved for" in r.message for r in caplog.records)

    def test_unapproved_rule_warns_in_soft_mode(self, tmp_path, caplog):
        spec = _make_spec(environment="prod", strict=False, rule_environments=["dev"])
        with caplog.at_level(logging.WARNING, logger="aml.engine.runner"):
            result = run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        # WARN landed.
        matched = [r for r in caplog.records if "is only approved for" in r.message]
        assert matched, "expected a WARN for the unapproved rule"
        assert "r1" in matched[0].message
        # And the run completed (no exception raised).
        assert "run_dir" in result.manifest

    def test_unapproved_rule_raises_in_strict_mode(self, tmp_path):
        spec = _make_spec(environment="prod", strict=True, rule_environments=["dev"])
        with pytest.raises(EnvironmentGatingError) as exc_info:
            run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        err = exc_info.value
        assert err.rule_id == "r1"
        assert err.environment == "prod"
        assert err.approved == ["dev"]

    def test_audit_ledger_records_every_gate_check(self, tmp_path):
        """The gate-check event lands for approved AND blocked rules so
        the regulator pack can prove the gate was consulted, not just
        that blocked rules existed."""
        spec = _make_spec(environment="dev", rule_environments=["dev"])
        result = run_spec(
            spec=spec,
            spec_path=_spec_path(spec, tmp_path),
            data={"txn": _sample_rows()},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        run_dir = Path(result.manifest["run_dir"])
        decisions = (run_dir / "decisions.jsonl").read_text().splitlines()
        gate_events = [
            json.loads(line)
            for line in decisions
            if json.loads(line).get("event") == "environment_gate_check"
        ]
        assert len(gate_events) == 1
        ev = gate_events[0]
        assert ev["rule_id"] == "r1"
        assert ev["program_environment"] == "dev"
        assert ev["approved"] is True
        assert ev["outcome"] == "approved"

    def test_strict_gating_records_blocked_event_before_raising(self, tmp_path):
        """Even when strict gating aborts the run, the audit ledger
        already carries the blocked event — the gate decision is
        evidence regardless of the abort."""
        spec = _make_spec(environment="prod", strict=True, rule_environments=["dev"])
        with pytest.raises(EnvironmentGatingError):
            run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        # The run dir was created by AuditLedger.create() before the
        # gate-check loop; find the most recent one under artifacts/.
        runs = sorted((tmp_path / "artifacts").rglob("decisions.jsonl"))
        assert runs, "expected a decisions.jsonl from the partial run"
        events = [json.loads(line) for line in runs[-1].read_text().splitlines()]
        gate = [e for e in events if e.get("event") == "environment_gate_check"]
        assert gate and gate[0]["outcome"] == "blocked"


# ---------------------------------------------------------------------------
# Spec diff
# ---------------------------------------------------------------------------


class TestSpecDiffSurfacesPromotionChanges:
    def test_program_environment_change_surfaces(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "program": {**raw["program"], "environment": "test"}}
        raw_b = {**raw, "program": {**raw["program"], "environment": "prod"}}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        env_changes = [c for c in result.program_changes if c.field == "environment"]
        assert env_changes and env_changes[0].before == "test"
        assert env_changes[0].after == "prod"

    def test_rule_environments_change_surfaces(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        rule_id = raw["rules"][0]["id"]
        raw_a = yaml.safe_load(yaml.safe_dump(raw))
        raw_a["rules"][0]["environments"] = ["dev"]
        raw_b = yaml.safe_load(yaml.safe_dump(raw))
        raw_b["rules"][0]["environments"] = ["dev", "test"]
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        mod = [r for r in result.rules_modified if r.id == rule_id]
        assert mod, f"expected rule {rule_id} in rules_modified"
        joined = " ".join(mod[0].changes)
        assert "environments" in joined
        assert "['dev']" in joined
        assert "['dev', 'test']" in joined
