"""Model-risk approval gate — issue #529 (Sub-feature C, Pillar 7).

Covers:
- pure gate predicates (`model_approval_gate_applies` /
  `is_rule_model_approved`) across the opt-in matrix;
- the `approval_gate_check` audit event envelope;
- runner integration: a material-tier (`model_tier` medium/high) rule
  still `pending` is BLOCKED in prod+strict+opted-in; an `approved` rule
  passes; the audit event is appended; the disabled path
  (`require_approval_before_prod=False`) is byte-identical to baseline;
- schema/model round-trip of the two new fields.
"""

from __future__ import annotations

import json
from datetime import date as _date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from aml_framework.engine.promotion import (
    EnvironmentGatingError,
    is_rule_model_approved,
    model_approval_audit_event,
    model_approval_gate_applies,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.loader import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    ModelRiskMonitoring,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _sample_rows() -> list[dict]:
    return [{"txn_id": "T1", "customer_id": "C0001", "amount": 100.0, "booked_at": _AS_OF}]


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


def _rule(
    *,
    model_tier: str | None = "medium",
    approval_status: str = "pending",
    environments: list[str] | None = None,
) -> Rule:
    return Rule(
        id="r1",
        name="R1",
        severity="high",
        risk_tier="high",
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
        model_tier=model_tier,
        approval_status=approval_status,
        environments=environments or ["dev"],
    )


def _make_spec(
    *,
    environment: str = "prod",
    strict: bool = True,
    require_approval: bool = True,
    model_tier: str | None = "medium",
    approval_status: str = "pending",
    rule_environments: list[str] | None = None,
) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
            environment=environment,
            strict_environment_gating=strict,
            model_risk_monitoring=ModelRiskMonitoring(
                enabled=True, require_approval_before_prod=require_approval
            ),
        ),
        data_contracts=[_txn_contract()],
        rules=[
            _rule(
                model_tier=model_tier,
                approval_status=approval_status,
                environments=rule_environments or ["dev", "prod"],
            )
        ],
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _spec_path(spec: AMLSpec, tmp_path: Path) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump(mode="json")))
    return path


# ---------------------------------------------------------------------------
# Pure predicates
# ---------------------------------------------------------------------------


class TestGateApplies:
    @pytest.mark.parametrize(
        ("environment", "strict", "require", "model_tier", "expected"),
        [
            ("prod", True, True, "medium", True),  # all conditions met
            ("prod", True, True, "high", True),
            ("prod", True, True, "low", False),  # immaterial tier never gated
            ("prod", True, True, None, False),  # no model tier
            ("prod", True, False, "medium", False),  # not opted in
            ("prod", False, True, "medium", False),  # not strict
            ("uat", True, True, "medium", False),  # not prod
            ("dev", True, True, "high", False),  # not prod
        ],
    )
    def test_matrix(self, environment, strict, require, model_tier, expected):
        spec = _make_spec(
            environment=environment,
            strict=strict,
            require_approval=require,
            model_tier=model_tier,
            # ensure the env-gate itself wouldn't fire (rule approved for lane)
            rule_environments=["dev", "test", "uat", "prod"],
        )
        assert model_approval_gate_applies(spec.rules[0], spec.program) is expected

    @pytest.mark.parametrize(
        ("status", "expected"),
        [("approved", True), ("pending", False), ("rejected", False)],
    )
    def test_is_rule_model_approved(self, status, expected):
        rule = _rule(approval_status=status)
        assert is_rule_model_approved(rule) is expected


class TestApprovalAuditEvent:
    def test_approved_event_shape(self):
        spec = _make_spec(approval_status="approved")
        ev = model_approval_audit_event(spec.rules[0], spec.program, approved=True)
        assert ev["event"] == "approval_gate_check"
        assert ev["rule_id"] == "r1"
        assert ev["model_tier"] == "medium"
        assert ev["approval_status"] == "approved"
        assert ev["approved"] is True
        assert ev["outcome"] == "approved"

    def test_blocked_event_shape(self):
        spec = _make_spec(approval_status="pending")
        ev = model_approval_audit_event(spec.rules[0], spec.program, approved=False)
        assert ev["approved"] is False
        assert ev["outcome"] == "blocked"
        assert ev["approval_status"] == "pending"


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


class TestRunnerApprovalGate:
    def test_pending_material_rule_blocked_in_prod_strict(self, tmp_path):
        spec = _make_spec(approval_status="pending")
        with pytest.raises(EnvironmentGatingError) as exc_info:
            run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        assert exc_info.value.rule_id == "r1"
        assert "approval" in str(exc_info.value).lower()

    def test_approved_material_rule_passes(self, tmp_path):
        spec = _make_spec(approval_status="approved")
        result = run_spec(
            spec=spec,
            spec_path=_spec_path(spec, tmp_path),
            data={"txn": _sample_rows()},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        # Run completed — no exception. And the approval gate event is
        # recorded as approved.
        run_dir = Path(result.manifest["run_dir"])
        events = [
            json.loads(line) for line in (run_dir / "decisions.jsonl").read_text().splitlines()
        ]
        gate = [e for e in events if e.get("event") == "approval_gate_check"]
        assert len(gate) == 1
        assert gate[0]["outcome"] == "approved"

    def test_blocked_event_appended_before_raising(self, tmp_path):
        spec = _make_spec(approval_status="pending")
        with pytest.raises(EnvironmentGatingError):
            run_spec(
                spec=spec,
                spec_path=_spec_path(spec, tmp_path),
                data={"txn": _sample_rows()},
                as_of=_AS_OF,
                artifacts_root=tmp_path / "artifacts",
            )
        runs = sorted((tmp_path / "artifacts").rglob("decisions.jsonl"))
        assert runs, "expected a decisions.jsonl from the partial run"
        events = [json.loads(line) for line in runs[-1].read_text().splitlines()]
        gate = [e for e in events if e.get("event") == "approval_gate_check"]
        assert gate and gate[0]["outcome"] == "blocked"

    def test_disabled_path_emits_no_approval_event(self, tmp_path):
        # require_approval_before_prod=False -> gate never applies, no
        # approval_gate_check event written (byte-identical baseline).
        spec = _make_spec(require_approval=False, approval_status="pending")
        result = run_spec(
            spec=spec,
            spec_path=_spec_path(spec, tmp_path),
            data={"txn": _sample_rows()},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        run_dir = Path(result.manifest["run_dir"])
        events = [
            json.loads(line) for line in (run_dir / "decisions.jsonl").read_text().splitlines()
        ]
        assert not [e for e in events if e.get("event") == "approval_gate_check"]

    def test_low_tier_pending_not_blocked(self, tmp_path):
        # An immaterial-tier (low) rule that is still pending must NOT be
        # blocked even in prod-strict with the gate opted in.
        spec = _make_spec(model_tier="low", approval_status="pending")
        result = run_spec(
            spec=spec,
            spec_path=_spec_path(spec, tmp_path),
            data={"txn": _sample_rows()},
            as_of=_AS_OF,
            artifacts_root=tmp_path / "artifacts",
        )
        run_dir = Path(result.manifest["run_dir"])
        events = [
            json.loads(line) for line in (run_dir / "decisions.jsonl").read_text().splitlines()
        ]
        assert not [e for e in events if e.get("event") == "approval_gate_check"]


# ---------------------------------------------------------------------------
# Schema / model round-trip
# ---------------------------------------------------------------------------


class TestSpecRoundTrip:
    def test_approval_status_defaults_to_pending(self):
        spec = load_spec(EXAMPLE)
        # The bundled demonstrator sets the scorer to approved; the other
        # rules default to pending.
        scorer = next(r for r in spec.rules if r.id == "passthrough_funnel_scorer")
        assert scorer.approval_status == "approved"
        other = next(r for r in spec.rules if r.id != "passthrough_funnel_scorer")
        assert other.approval_status == "pending"

    def test_require_approval_round_trips(self):
        spec = load_spec(EXAMPLE)
        assert spec.program.model_risk_monitoring.require_approval_before_prod is True

    def test_invalid_approval_status_rejected(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["approval_status"] = "maybe"  # not in enum
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)
