"""PR-PAY-1 — uniform `threshold` + `reference_data_version` on every alert.

Pins the Pillar-6 (alert lifecycle & explainability) contract: every
alert emitted by the engine, regardless of rule logic type, must carry
both `threshold` and `reference_data_version` keys. The metadata flows
through `record_alerts` to `alerts/<rule_id>.jsonl` AND lands on the
final `cases/<case_id>.json` so an investigator can answer "why did
this fire on this date?" without re-reading the spec.

Coverage map (one test class per rule logic type + helper-level units):
  * aggregation_window — `having` block echoed verbatim
  * list_match         — `match` + `threshold` + reference_data_version
  * network_pattern    — `pattern` + `max_hops` + `having`
  * custom_sql         — both fields present but `threshold` is None
  * python_ref         — both fields present but `threshold` is None
  * helpers            — `alert_threshold_snapshot` + `reference_data_version`
  * case files         — payload meta survives `_build_case` round-trip
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.engine.payload_meta import (
    alert_threshold_snapshot,
    reference_data_version,
    reference_data_version_from_bytes,
    stamp_payload_meta,
)
from aml_framework.engine.runner import (
    _execute_list_match,
    _execute_network_pattern,
    _harden_duckdb,
)
from aml_framework.spec import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    CustomSQLLogic,
    ListMatchLogic,
    NetworkPatternLogic,
    PythonRefLogic,
    RegulationRef,
    Rule,
)

SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Helper-level unit tests
# ---------------------------------------------------------------------------


def _rule(logic) -> Rule:
    return Rule(
        id="r_test",
        name="Test rule",
        severity="high",
        regulation_refs=[RegulationRef(citation="x", description="y")],
        logic=logic,
        escalate_to="q",
    )


class TestAlertThresholdSnapshot:
    def test_aggregation_window_returns_having_block(self):
        rule = _rule(
            AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 3}},
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {"having": {"count": {"gte": 3}}}

    def test_list_match_fuzzy_returns_score_floor(self):
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.85,
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {"match": "fuzzy", "threshold": 0.85}

    def test_list_match_fuzzy_omitted_threshold_uses_runner_default(self):
        """Codex review (pass 1, blocker #2): when `logic.threshold` is
        None on a fuzzy rule, `_execute_list_match` substitutes 0.8.
        The snapshot must report the effective threshold the rule
        actually fired at — reporting None would mislead investigators."""
        from aml_framework.engine.payload_meta import DEFAULT_FUZZY_THRESHOLD

        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                # threshold omitted — schema allows it.
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {"match": "fuzzy", "threshold": DEFAULT_FUZZY_THRESHOLD}

    def test_list_match_fuzzy_explicit_zero_threshold_is_honoured(self):
        """Codex review (pass 2, blocker #2): the spec YAML is the
        source of truth. An explicit `threshold: 0.0` must NOT be
        silently rewritten to 0.8 — that would lie about what the rule
        fired at. The runner's `or 0.8` fallback was tightened to
        `is None` to enforce this; the snapshot mirrors that."""
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.0,
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {"match": "fuzzy", "threshold": 0.0}

    def test_list_match_exact_preserves_none_threshold(self):
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="exact",
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {"match": "exact", "threshold": None}

    def test_network_pattern_returns_pattern_hops_having(self):
        rule = _rule(
            NetworkPatternLogic(
                type="network_pattern",
                source="customer",
                pattern="component_size",
                max_hops=3,
                having={"component_size": {"gte": 4}},
            )
        )
        snap = alert_threshold_snapshot(rule)
        assert snap == {
            "pattern": "component_size",
            "max_hops": 3,
            "having": {"component_size": {"gte": 4}},
        }

    def test_custom_sql_returns_none(self):
        rule = _rule(CustomSQLLogic(type="custom_sql", sql="SELECT 1"))
        assert alert_threshold_snapshot(rule) is None

    def test_python_ref_returns_none(self):
        rule = _rule(
            PythonRefLogic(
                type="python_ref",
                callable="aml_framework.models.scoring:heuristic_risk_scorer",
                model_id="m1",
                model_version="1.0",
            )
        )
        assert alert_threshold_snapshot(rule) is None


class TestReferenceDataVersion:
    def test_list_match_returns_fingerprint(self, tmp_path: Path):
        lists_dir = tmp_path / "lists"
        lists_dir.mkdir()
        list_path = lists_dir / "mylist.csv"
        list_path.write_text("name\nALICE\nBOB\n", encoding="utf-8")
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="mylist",
                match="fuzzy",
                threshold=0.8,
            )
        )
        version = reference_data_version(rule, as_of=datetime(2026, 4, 23), lists_dir=lists_dir)
        assert version is not None
        assert version.startswith("mylist@")
        # 16-char hex suffix.
        suffix = version.split("@", 1)[1]
        assert len(suffix) == 16
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_list_match_missing_file_returns_none(self, tmp_path: Path):
        lists_dir = tmp_path / "lists"
        lists_dir.mkdir()
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="nonexistent",
                match="exact",
            )
        )
        assert (
            reference_data_version(rule, as_of=datetime(2026, 4, 23), lists_dir=lists_dir) is None
        )

    def test_content_change_changes_fingerprint(self, tmp_path: Path):
        lists_dir = tmp_path / "lists"
        lists_dir.mkdir()
        list_path = lists_dir / "mylist.csv"
        list_path.write_text("name\nALICE\n", encoding="utf-8")
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="mylist",
                match="exact",
            )
        )
        v1 = reference_data_version(rule, as_of=datetime(2026, 4, 23), lists_dir=lists_dir)
        list_path.write_text("name\nALICE\nBOB\n", encoding="utf-8")
        v2 = reference_data_version(rule, as_of=datetime(2026, 4, 23), lists_dir=lists_dir)
        assert v1 != v2

    def test_non_list_match_rule_returns_none(self):
        rule = _rule(CustomSQLLogic(type="custom_sql", sql="SELECT 1"))
        assert reference_data_version(rule, as_of=datetime(2026, 4, 23)) is None

    def test_aggregation_window_rule_returns_none(self):
        rule = _rule(
            AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 3}},
            )
        )
        assert reference_data_version(rule, as_of=datetime(2026, 4, 23)) is None


class TestStampPayloadMeta:
    def test_engine_owned_keys_overwrite_executor_output(self):
        """Codex review (pass 1, blocker #1): the audit contract is
        engine-owned; an executor-projected `threshold` column (e.g.
        from a custom_sql SELECT) must NOT win over the spec-derived
        snapshot — otherwise Pillar 6's "uniform contract" claim is a
        lie."""
        rule = _rule(
            AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 3}},
            )
        )
        alerts = [
            {"customer_id": "C1", "threshold": "executor_smuggled_value"},
        ]
        stamp_payload_meta(rule, alerts, as_of=datetime(2026, 4, 23))
        # Engine-owned value wins.
        assert alerts[0]["threshold"] == {"having": {"count": {"gte": 3}}}
        assert "reference_data_version" in alerts[0]

    def test_empty_alert_list_is_noop(self):
        rule = _rule(CustomSQLLogic(type="custom_sql", sql="SELECT 1"))
        out = stamp_payload_meta(rule, [], as_of=datetime(2026, 4, 23))
        assert out == []

    def test_override_pins_version_to_matched_bytes(self):
        """Codex pass-5 race fix: when the executor has already
        digested the bytes it screened against, the override pins the
        alert payload to that exact value — preventing a mid-run list
        refresh from making the alert cite a snapshot different from
        the one it was matched against."""
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.8,
            )
        )
        alerts = [{"customer_id": "C1"}]
        stamp_payload_meta(
            rule,
            alerts,
            as_of=datetime(2026, 4, 23),
            reference_data_version_override="sanctions@deadbeefcafef00d",
        )
        assert alerts[0]["reference_data_version"] == "sanctions@deadbeefcafef00d"

    def test_reference_data_version_from_bytes_matches_file_hash(self, tmp_path: Path):
        """The bytes-based helper must produce the same fingerprint as
        the file-based helper for identical content — that's what makes
        the override race-free contract sound."""
        lists_dir = tmp_path / "lists"
        lists_dir.mkdir()
        list_path = lists_dir / "mylist.csv"
        content = b"name\nALICE\nBOB\n"
        list_path.write_bytes(content)
        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="mylist",
                match="exact",
            )
        )
        from_file = reference_data_version(rule, as_of=datetime(2026, 4, 23), lists_dir=lists_dir)
        from_bytes = reference_data_version_from_bytes("mylist", content)
        assert from_file == from_bytes

    def test_stamp_does_not_add_rule_version_to_alert(self):
        """`rule_version` is surfaced at the **case** level (by
        `_build_case`), not the alert level. Stamping it on the alert
        would couple alert hashes to spec-metadata-only changes such as
        `evaluation_mode: streaming`, breaking the
        `test_engine_runs_batch_regardless_of_field` invariant. The
        helper must NOT add it here."""
        rule = _rule(
            AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 3}},
            )
        )
        alerts = [{"customer_id": "C1"}]
        stamp_payload_meta(rule, alerts, as_of=datetime(2026, 4, 23))
        assert "rule_version" not in alerts[0]


# ---------------------------------------------------------------------------
# Engine-level integration tests — every alert from every rule path
# carries `threshold` + `reference_data_version`.
# ---------------------------------------------------------------------------


def _run(tmp_path, spec_path):
    spec = load_spec(spec_path)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return spec, run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of,
        artifacts_root=tmp_path,
    )


class TestRunnerStampsAllRulePaths:
    """Every alert across every executable rule logic type must carry
    `threshold` + `reference_data_version` keys (value may be None)."""

    def test_every_alert_has_uniform_payload_meta_keys(self, tmp_path):
        _, result = _run(tmp_path, SPEC_CA)
        assert result.total_alerts > 0
        for rule_id, alerts in result.alerts.items():
            for alert in alerts:
                assert "threshold" in alert, f"alert from rule {rule_id!r} missing 'threshold' key"
                assert "reference_data_version" in alert, (
                    f"alert from rule {rule_id!r} missing 'reference_data_version' key"
                )

    def test_every_case_file_has_rule_version(self, tmp_path):
        """Codex pass-3 follow-up: `rule_version` lives on the case
        file (not the alert), same hash the audit ledger uses on
        `case_opened` decisions. Lets the Case Investigation 'Rule
        version' metric render without a ledger lookup."""
        from aml_framework.engine.audit import rule_version_hash

        spec, result = _run(tmp_path, SPEC_CA)
        rule_by_id = {r.id: r for r in spec.rules}
        run_dir = Path(result.manifest["run_dir"])
        case_files = list((run_dir / "cases").glob("*.json"))
        assert case_files, "the run must produce at least one case file"
        for case_path in case_files:
            case = json.loads(case_path.read_bytes())
            rule = rule_by_id[case["rule_id"]]
            assert case.get("rule_version") == rule_version_hash(rule)

    def test_aggregation_window_alert_threshold_echoes_having(self, tmp_path):
        spec, result = _run(tmp_path, SPEC_US)
        rule_by_id = {r.id: r for r in spec.rules}
        # Find any aggregation_window rule that fired.
        for rule_id, alerts in result.alerts.items():
            rule = rule_by_id[rule_id]
            if rule.logic.type != "aggregation_window" or not alerts:
                continue
            alert = alerts[0]
            assert alert["threshold"] == {"having": dict(rule.logic.having)}
            return
        pytest.skip("no aggregation_window alerts fired on community_bank spec")

    def test_list_match_alert_carries_reference_data_version(self, tmp_path):
        _, result = _run(tmp_path, SPEC_CA)
        alerts = result.alerts.get("sanctions_screening", [])
        assert alerts, "sanctions_screening should fire on planted C0003"
        for alert in alerts:
            assert alert["threshold"] == {"match": "fuzzy", "threshold": 0.8}
            ref = alert["reference_data_version"]
            assert ref is not None
            assert ref.startswith("sanctions@")

    def test_list_match_alert_threshold_is_dict_not_float(self, tmp_path):
        """Regression guard: the legacy ListMatch payload exposed a
        bare float `match_score`; the uniform `threshold` field is the
        rule's score floor, not the per-alert score."""
        _, result = _run(tmp_path, SPEC_CA)
        alerts = result.alerts.get("sanctions_screening", [])
        if not alerts:
            pytest.skip("no sanctions alerts produced")
        for alert in alerts:
            # `match_score` (per-alert) and `threshold` (rule snapshot)
            # are now distinct keys with distinct semantics.
            assert isinstance(alert["threshold"], dict)
            assert "match_score" in alert  # legacy field preserved
            assert alert["match_score"] >= 0.8

    def test_case_files_carry_payload_meta(self, tmp_path):
        """Pillar-6 evidence-trail integrity: the metadata must survive
        the alert → case round-trip and land on `cases/<case_id>.json`."""
        _, result = _run(tmp_path, SPEC_CA)
        run_dir = Path(result.manifest["run_dir"])
        case_files = list((run_dir / "cases").glob("*.json"))
        assert case_files, "the run must produce at least one case file"
        for case_path in case_files:
            case = json.loads(case_path.read_bytes())
            alert = case["alert"]
            assert "threshold" in alert
            assert "reference_data_version" in alert

    def test_alerts_jsonl_carries_payload_meta(self, tmp_path):
        """The ledger's on-disk `alerts/<rule_id>.jsonl` is the audit-
        side source of truth; the metadata must land there too."""
        _, result = _run(tmp_path, SPEC_CA)
        run_dir = Path(result.manifest["run_dir"])
        jsonl_files = [p for p in (run_dir / "alerts").glob("*.jsonl") if p.stat().st_size > 0]
        assert jsonl_files, "at least one rule must have non-empty alerts.jsonl"
        for path in jsonl_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                alert = json.loads(line)
                assert "threshold" in alert
                assert "reference_data_version" in alert


# ---------------------------------------------------------------------------
# Per-executor tests — call the rule executors directly to pin the
# stamping for the network_pattern and list_match shapes that the live
# specs may not exercise on every rule variant.
# ---------------------------------------------------------------------------


class TestNetworkPatternStamp:
    def test_network_pattern_alerts_get_threshold_after_stamp(self):
        con = duckdb.connect(":memory:")
        _harden_duckdb(con)
        con.execute("CREATE TABLE customer (customer_id VARCHAR)")
        con.executemany(
            "INSERT INTO customer (customer_id) VALUES (?)",
            [("A",), ("B",), ("C",)],
        )
        con.execute(
            "CREATE TABLE resolved_entity_link"
            " (left_customer_id VARCHAR, right_customer_id VARCHAR,"
            "  attribute VARCHAR, weight DOUBLE)"
        )
        con.executemany(
            "INSERT INTO resolved_entity_link VALUES (?, ?, ?, 1.0)",
            [("A", "B", "phone"), ("B", "C", "phone")],
        )
        rule = _rule(
            NetworkPatternLogic(
                type="network_pattern",
                source="customer",
                pattern="component_size",
                max_hops=2,
                having={"component_size": {"gte": 3}},
            )
        )
        alerts = _execute_network_pattern(rule, con, datetime(2026, 1, 1))
        # Per-executor pre-stamp: the raw output does NOT carry the
        # uniform fields — those are added by `stamp_payload_meta`.
        stamp_payload_meta(rule, alerts, as_of=datetime(2026, 1, 1))
        assert alerts
        for a in alerts:
            assert a["threshold"] == {
                "pattern": "component_size",
                "max_hops": 2,
                "having": {"component_size": {"gte": 3}},
            }
            # network_pattern reads no reference list.
            assert a["reference_data_version"] is None
        con.close()


class TestListMatchStamp:
    def test_list_match_executor_alerts_take_uniform_threshold(self, tmp_path: Path):
        # Build an isolated reference list in a tmp dir and point the
        # helper at it via lists_dir argument; the executor itself reads
        # from REFERENCE_LISTS_DIR so we use a list name that exists
        # there (sanctions).
        from aml_framework.paths import REFERENCE_LISTS_DIR

        rule = _rule(
            ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.85,
            )
        )
        con = duckdb.connect(":memory:")
        _harden_duckdb(con)
        con.execute("CREATE TABLE customer (customer_id VARCHAR, full_name VARCHAR)")
        # Read a real name from the sanctions list to guarantee a hit.
        sample_name = None
        sanctions_path = REFERENCE_LISTS_DIR / "sanctions.csv"
        with sanctions_path.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("name"):
                    sample_name = row["name"]
                    break
        assert sample_name, "sanctions.csv must have at least one name row"
        con.execute(
            "INSERT INTO customer (customer_id, full_name) VALUES (?, ?)",
            ["C9999", sample_name],
        )
        alerts = _execute_list_match(rule, con, datetime(2026, 1, 1))
        stamp_payload_meta(rule, alerts, as_of=datetime(2026, 1, 1))
        assert alerts, "the fuzzy match must produce at least one alert"
        for a in alerts:
            assert a["threshold"] == {"match": "fuzzy", "threshold": 0.85}
            ref = a["reference_data_version"]
            assert ref is not None and ref.startswith("sanctions@")
        con.close()
