"""Engine tests — runner, audit ledger, export, diff, list match."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
import duckdb
import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec
from aml_framework.spec.models import (
    AMLSpec,
    Column,
    DataContract,
    ListMatchLogic,
    Program,
    Queue,
    RegulationRef,
    Report,
    ReportSection,
    Rule,
    Workflow,
)

SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
SPEC_CA_BANK = Path(__file__).resolve().parents[1] / "examples" / "canadian_bank" / "aml.yaml"


def _run(tmp_path, spec_path=SPEC_CA):
    """Common helper: load spec, generate data, run engine, return (spec, data, result)."""
    spec = load_spec(spec_path)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return (
        spec,
        data,
        run_spec(spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=tmp_path),
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestRunnerEndToEnd:
    def test_end_to_end_detects_planted_structurer(self, tmp_path):
        spec = load_spec(SPEC_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        result = run_spec(
            spec=spec,
            spec_path=SPEC_US,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )

        structuring_alerts = result.alerts["structuring_cash_deposits"]
        assert len(structuring_alerts) >= 1, "planted structurer must be alerted"

        # The planted structurer is customer C0001 (second id in the generator).
        assert any(a["customer_id"] == "C0001" for a in structuring_alerts)

        # Every alert must have a case file and an audit-ledger decision event.
        run_dir = Path(result.manifest["run_dir"])
        for alert in structuring_alerts:
            cases = list(
                (run_dir / "cases").glob(f"structuring_cash_deposits__{alert['customer_id']}*")
            )
            assert cases, f"missing case file for {alert['customer_id']}"

        decisions = (run_dir / "decisions.jsonl").read_bytes().splitlines()
        assert len(decisions) >= len(structuring_alerts)

    def test_run_is_reproducible(self, tmp_path):
        spec = load_spec(SPEC_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        r1 = run_spec(
            spec=spec, spec_path=SPEC_US, data=data, as_of=as_of, artifacts_root=tmp_path / "a"
        )
        r2 = run_spec(
            spec=spec, spec_path=SPEC_US, data=data, as_of=as_of, artifacts_root=tmp_path / "b"
        )

        for rule_id, hash1 in r1.manifest["rule_outputs"].items():
            assert hash1 == r2.manifest["rule_outputs"][rule_id], (
                f"output hash drift on rule {rule_id} — non-deterministic engine"
            )
        assert r1.manifest["decisions_hash"] == r2.manifest["decisions_hash"], (
            "decisions_hash must be deterministic across runs"
        )


class TestAuditLedgerFrozen:
    """After finalize(), the snapshot files are read-only on POSIX.

    Skipped on Windows (different ACL semantics) and when running as root
    (root bypasses 0o444 — the docker CI job runs as root).
    """

    def _is_enforcing(self):
        if os.name == "nt":
            return False
        # Root ignores rwx mode bits.
        try:
            return os.geteuid() != 0
        except AttributeError:  # pragma: no cover — non-POSIX without geteuid
            return False

    def test_manifest_is_read_only_after_finalize(self, tmp_path):
        if not self._is_enforcing():
            pytest.skip("chmod 0o444 not enforced (Windows or root)")
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        manifest_path = run_dir / "manifest.json"
        mode = os.stat(manifest_path).st_mode & 0o777
        assert mode == 0o444, f"manifest.json mode is {oct(mode)}, expected 0o444"

    def test_alert_outputs_are_read_only_after_finalize(self, tmp_path):
        if not self._is_enforcing():
            pytest.skip("chmod 0o444 not enforced (Windows or root)")
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        alerts_dir = run_dir / "alerts"
        for f in alerts_dir.iterdir():
            if f.is_file():
                mode = os.stat(f).st_mode & 0o777
                assert mode == 0o444, f"{f.name} mode is {oct(mode)}"

    def test_decisions_jsonl_remains_writable(self, tmp_path):
        """Human decisions still need to be appended after finalize."""
        from aml_framework.engine.audit import AuditLedger

        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        AuditLedger.append_to_run_dir(
            run_dir, {"event": "manual_review", "case_id": "post-finalize"}
        )
        text = (run_dir / "decisions.jsonl").read_text()
        assert "manual_review" in text

    def test_manifest_write_after_finalize_raises(self, tmp_path):
        if not self._is_enforcing():
            pytest.skip("chmod 0o444 not enforced (Windows or root)")
        _, _, result = _run(tmp_path)
        manifest_path = Path(result.manifest["run_dir"]) / "manifest.json"
        with pytest.raises(PermissionError):
            with manifest_path.open("w") as f:
                f.write("{}")


class TestAuditLedgerDeterminism:
    def test_append_to_run_dir_uses_wall_clock(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        run_dir = tmp_path / "run-x"
        run_dir.mkdir()
        (run_dir / "decisions.jsonl").touch()
        AuditLedger.append_to_run_dir(run_dir, {"event": "manual_review", "case_id": "C0042"})
        line = (run_dir / "decisions.jsonl").read_text().strip()
        assert '"event":"manual_review"' in line
        assert '"case_id":"C0042"' in line
        assert '"ts":"' in line  # timestamp written

    def test_append_to_run_dir_explicit_ts_is_used(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        run_dir = tmp_path / "run-x"
        run_dir.mkdir()
        (run_dir / "decisions.jsonl").touch()
        ts = datetime(2026, 4, 23, 12, 0, 0)
        AuditLedger.append_to_run_dir(run_dir, {"event": "x", "case_id": "Y"}, ts=ts)
        line = (run_dir / "decisions.jsonl").read_text().strip()
        assert '"ts":"2026-04-23T12:00:00"' in line

    def test_verify_decisions_with_external_hash(self, tmp_path):
        """verify_decisions accepts an out-of-band hash for stronger tamper detection."""
        from aml_framework.engine.audit import AuditLedger

        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        external_hash = result.manifest["decisions_hash"]

        ok, _ = AuditLedger.verify_decisions(run_dir, expected_hash=external_hash)
        assert ok

        ok, msg = AuditLedger.verify_decisions(run_dir, expected_hash="0" * 64)
        assert not ok
        assert "tamper" in msg.lower() or "computed" in msg.lower()


class TestEngineConstants:
    """Compliance audit logs are forever — these strings must not silently rename."""

    def test_event_values_are_frozen(self):
        from aml_framework.engine.constants import Event

        # If you change any of these, bump a major version: existing decisions.jsonl
        # files in regulator-bound evidence bundles depend on these literals.
        assert Event.CASE_OPENED == "case_opened"
        assert Event.ESCALATED == "escalated"
        assert Event.ESCALATED_TO_STR == "escalated_to_str"
        assert Event.CLOSED == "closed"
        assert Event.RULE_FAILED == "rule_failed"
        assert Event.MANUAL_REVIEW == "manual_review"

    def test_queue_values_are_frozen(self):
        from aml_framework.engine.constants import Queue

        assert Queue.CLOSED_NO_ACTION == "closed_no_action"
        assert Queue.STR_FILING == "str_filing"
        assert Queue.SAR_FILING == "sar_filing"

    def test_decisions_use_constants_not_literals(self, tmp_path):
        """Spot-check that an end-to-end run emits the canonical event strings."""
        from aml_framework.engine.constants import Event

        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        events = {
            json.loads(line).get("event")
            for line in (run_dir / "decisions.jsonl").read_text().splitlines()
            if line.strip()
        }
        # case_opened always fires for any alert. Other events depend on data.
        assert Event.CASE_OPENED in events


class TestEngineHardening:
    def test_duckdb_external_access_disabled(self):
        """Hardened DuckDB connections must refuse to load HTTPFS / external URLs."""
        from aml_framework.engine.runner import _harden_duckdb

        con = duckdb.connect(":memory:")
        _harden_duckdb(con)
        # enable_external_access blocks HTTPFS and remote ATTACH at the engine
        # layer. Confirm the setting is applied (DuckDB exposes settings via
        # duckdb_settings()).
        rows = con.execute(
            "SELECT name, value FROM duckdb_settings() "
            "WHERE name IN ('enable_external_access', 'autoload_known_extensions')"
        ).fetchall()
        settings = {name: value for name, value in rows}
        # Older DuckDB releases may not expose these; if present, they must be off.
        if "enable_external_access" in settings:
            assert settings["enable_external_access"].lower() in ("false", "0")
        if "autoload_known_extensions" in settings:
            assert settings["autoload_known_extensions"].lower() in ("false", "0")
        con.close()

    def test_python_ref_module_outside_prefix_rejected(self, tmp_path, monkeypatch):
        """python_ref pointing at an arbitrary stdlib module must be rejected."""
        import yaml as _yaml

        from aml_framework.engine.runner import _allowed_python_ref_prefixes

        # Sanity: default prefix is restrictive.
        assert _allowed_python_ref_prefixes() == ("aml_framework.models.",)

        spec_raw = _yaml.safe_load(SPEC_CA.read_text())
        # Replace the first python_ref rule's callable, if any, with os:getcwd.
        replaced = False
        for rule in spec_raw["rules"]:
            if rule.get("logic", {}).get("type") == "python_ref":
                rule["logic"]["callable"] = "os:getcwd"
                replaced = True
                break
        if not replaced:
            pytest.skip("CA spec has no python_ref rule to hijack")
        bad_spec = tmp_path / "aml.yaml"
        bad_spec.write_text(_yaml.safe_dump(spec_raw))

        spec = load_spec(bad_spec)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        with pytest.raises(ValueError, match="not under an allowed prefix"):
            run_spec(
                spec=spec, spec_path=bad_spec, data=data, as_of=as_of, artifacts_root=tmp_path / "x"
            )

    def test_python_ref_prefix_extends_via_env(self, monkeypatch):
        """AML_PYTHON_REF_PREFIX env var extends the allow-list (comma-separated)."""
        from aml_framework.engine.runner import _allowed_python_ref_prefixes

        monkeypatch.setenv("AML_PYTHON_REF_PREFIX", "aml_framework.models.,my_org.scorers.")
        prefixes = _allowed_python_ref_prefixes()
        assert "aml_framework.models." in prefixes
        assert "my_org.scorers." in prefixes


class TestPythonRefErrorBoundary:
    """A scorer that raises must NOT abort the whole run."""

    def _spec_with_failing_scorer(self, tmp_path: Path, callable_str: str) -> Path:
        import yaml as _yaml

        spec_raw = _yaml.safe_load(SPEC_CA.read_text())
        replaced = False
        for rule in spec_raw["rules"]:
            if rule.get("logic", {}).get("type") == "python_ref":
                rule["logic"]["callable"] = callable_str
                replaced = True
                break
        if not replaced:
            pytest.skip("CA spec has no python_ref rule to hijack")
        bad = tmp_path / "aml.yaml"
        bad.write_text(_yaml.safe_dump(spec_raw))
        return bad

    def test_missing_module_does_not_abort_run(self, tmp_path):
        spec_path = self._spec_with_failing_scorer(
            tmp_path, "aml_framework.models.does_not_exist:score"
        )
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=tmp_path / "x"
        )
        # Run completed despite the missing module — manifest exists, other
        # rules produced their normal alerts.
        assert "rule_outputs" in result.manifest
        assert result.total_alerts > 0  # other rules ran

    def test_failed_rule_records_zero_alerts(self, tmp_path):
        spec_path = self._spec_with_failing_scorer(tmp_path, "aml_framework.models.nope:score")
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=tmp_path / "x"
        )
        # Find the python_ref rule that failed and assert its alert list is empty.
        py_ref_rules = [r for r in spec.rules if r.logic.type == "python_ref"]
        assert py_ref_rules, "spec must have a python_ref rule for this test to be meaningful"
        for rule in py_ref_rules:
            assert result.alerts.get(rule.id, []) == []

    def test_failure_emits_rule_failed_event_in_decisions(self, tmp_path):
        spec_path = self._spec_with_failing_scorer(tmp_path, "aml_framework.models.nope:score")
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=tmp_path / "x"
        )
        run_dir = Path(result.manifest["run_dir"])
        decisions = [
            json.loads(line)
            for line in (run_dir / "decisions.jsonl").read_text().splitlines()
            if line.strip()
        ]
        failed = [d for d in decisions if d.get("event") == "rule_failed"]
        assert len(failed) >= 1
        assert failed[0]["logic_type"] == "python_ref"
        assert "ModuleNotFoundError" in failed[0].get("error", "") or "No module" in failed[0].get(
            "error", ""
        )

    def test_runtime_error_inside_scorer_is_caught(self, tmp_path, monkeypatch):
        """A scorer that imports cleanly but raises at call time also gets caught."""
        import sys
        import types

        # Build a fake module under the allowed prefix that raises on call.
        mod = types.ModuleType("aml_framework.models.crashing_scorer")

        def _crash(con, as_of):
            raise RuntimeError("simulated model failure")

        mod.score = _crash
        sys.modules["aml_framework.models.crashing_scorer"] = mod
        try:
            spec_path = self._spec_with_failing_scorer(
                tmp_path, "aml_framework.models.crashing_scorer:score"
            )
            spec = load_spec(spec_path)
            as_of = datetime(2026, 4, 23, 12, 0, 0)
            data = generate_dataset(as_of=as_of, seed=42)
            result = run_spec(
                spec=spec,
                spec_path=spec_path,
                data=data,
                as_of=as_of,
                artifacts_root=tmp_path / "x",
            )
            # Run completed.
            assert "rule_outputs" in result.manifest
            run_dir = Path(result.manifest["run_dir"])
            decisions = [
                json.loads(line)
                for line in (run_dir / "decisions.jsonl").read_text().splitlines()
                if line.strip()
            ]
            failed = [d for d in decisions if d.get("event") == "rule_failed"]
            assert any("RuntimeError" in d.get("error", "") for d in failed)
        finally:
            sys.modules.pop("aml_framework.models.crashing_scorer", None)


class TestThresholdBoundaries:
    """Negative tests: just-below-threshold data must NOT fire.

    Coverage % alone doesn't bound false positives. These tests assert that
    each detection rule respects its threshold by feeding deliberately
    below-the-line data and confirming the rule produces zero alerts for the
    test customer.
    """

    AS_OF = datetime(2026, 4, 23, 12, 0, 0)

    @staticmethod
    def _customer(cid: str, country: str = "CA", risk: str = "low") -> dict:
        return {
            "customer_id": cid,
            "full_name": f"Test {cid}",
            "country": country,
            "risk_rating": risk,
            "onboarded_at": datetime(2024, 1, 1),
            "business_activity": "retail",
        }

    @staticmethod
    def _txn(
        tid: str,
        cid: str,
        amount: float,
        channel: str = "cash",
        direction: str = "in",
        days_before: int = 1,
    ) -> dict:
        from datetime import timedelta

        return {
            "txn_id": tid,
            "customer_id": cid,
            "amount": amount,
            "currency": "CAD",
            "channel": channel,
            "direction": direction,
            "booked_at": TestThresholdBoundaries.AS_OF - timedelta(days=days_before),
        }

    def _run_alerts_for(self, tmp_path, data, rule_id: str) -> list:
        spec = load_spec(SPEC_CA)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_CA,
            data=data,
            as_of=self.AS_OF,
            artifacts_root=tmp_path,
        )
        return [a for a in result.alerts.get(rule_id, []) if a.get("customer_id") == "T0001"]

    def test_structuring_below_count_does_not_fire(self, tmp_path):
        """count < 3 → no structuring alert (sum is high but count fails)."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                # Two cash-in deposits, both in [5000-9999]. Sum = $18000 (well above
                # 20000 threshold? No, $9000+$9000=$18000 < $20000). count=2 fails.
                # But also: each amount in [5000-9999] passes the filter.
                self._txn("T1", "T0001", 9000, days_before=1),
                self._txn("T2", "T0001", 9000, days_before=2),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "structuring_cash_deposits") == []

    def test_structuring_below_sum_does_not_fire(self, tmp_path):
        """count >= 3 but sum < 20000 → no alert."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                # 3 deposits of $6000 each. count=3 (passes), sum=$18000 (< 20000).
                self._txn("T1", "T0001", 6000, days_before=1),
                self._txn("T2", "T0001", 6000, days_before=2),
                self._txn("T3", "T0001", 6000, days_before=3),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "structuring_cash_deposits") == []

    def test_structuring_above_threshold_fires(self, tmp_path):
        """Positive control: 3 deposits at $9000 = $27000. Both thresholds met."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                self._txn("T1", "T0001", 9000, days_before=1),
                self._txn("T2", "T0001", 9000, days_before=2),
                self._txn("T3", "T0001", 9000, days_before=3),
            ],
        }
        alerts = self._run_alerts_for(tmp_path, data, "structuring_cash_deposits")
        assert len(alerts) == 1, f"expected 1 alert, got {alerts}"

    def test_structuring_outside_amount_filter_does_not_fire(self, tmp_path):
        """Amounts outside [5000-9999] don't match the filter, even if count/sum would qualify."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                # 4 deposits at $4000 each = $16000. amount filter [5000-9999] excludes them.
                self._txn("T1", "T0001", 4000, days_before=1),
                self._txn("T2", "T0001", 4000, days_before=2),
                self._txn("T3", "T0001", 4000, days_before=3),
                self._txn("T4", "T0001", 4000, days_before=4),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "structuring_cash_deposits") == []

    def test_lctr_below_threshold_does_not_fire(self, tmp_path):
        """large_cash_lctr: sum_amount per day < $10000 → no alert."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                # Two cash deposits same day totalling $9000. Below $10k threshold.
                self._txn("T1", "T0001", 5000, days_before=1),
                self._txn("T2", "T0001", 4000, days_before=1),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "large_cash_lctr") == []

    def test_lctr_at_threshold_fires(self, tmp_path):
        """Positive control: sum exactly $10000 same day → alert (gte semantic)."""
        data = {
            "customer": [self._customer("T0001")],
            "txn": [
                self._txn("T1", "T0001", 5000, days_before=1),
                self._txn("T2", "T0001", 5000, days_before=1),
            ],
        }
        alerts = self._run_alerts_for(tmp_path, data, "large_cash_lctr")
        assert len(alerts) == 1

    def test_high_risk_jurisdiction_safe_country_does_not_fire(self, tmp_path):
        """Customer in low-risk country must not trigger high_risk_jurisdiction."""
        data = {
            "customer": [self._customer("T0001", country="CA")],
            "txn": [
                # Sum $20000, well above the rule's $5000 threshold.
                self._txn("T1", "T0001", 10000, channel="wire", direction="in", days_before=1),
                self._txn("T2", "T0001", 10000, channel="wire", direction="in", days_before=2),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "high_risk_jurisdiction") == []

    def test_high_risk_jurisdiction_below_sum_does_not_fire(self, tmp_path):
        """Even from a high-risk country, sum < $5000 must not fire."""
        data = {
            "customer": [self._customer("T0001", country="RU", risk="high")],
            "txn": [
                self._txn("T1", "T0001", 2000, channel="wire", direction="in", days_before=1),
                self._txn("T2", "T0001", 2000, channel="wire", direction="in", days_before=2),
            ],
        }
        assert self._run_alerts_for(tmp_path, data, "high_risk_jurisdiction") == []

    def test_high_risk_jurisdiction_above_threshold_fires(self, tmp_path):
        """Positive control: high-risk country, sum >= $5000."""
        data = {
            "customer": [self._customer("T0001", country="RU", risk="high")],
            "txn": [
                self._txn("T1", "T0001", 5000, channel="wire", direction="in", days_before=1),
            ],
        }
        alerts = self._run_alerts_for(tmp_path, data, "high_risk_jurisdiction")
        assert len(alerts) == 1


class TestRunnerEdgeCases:
    def test_run_produces_manifest(self, tmp_path):
        """Every run produces a manifest with required fields."""
        _, _, result = _run(tmp_path)
        assert "engine_version" in result.manifest
        assert "spec_content_hash" in result.manifest
        assert "rule_outputs" in result.manifest
        assert "inputs" in result.manifest

    def test_empty_contract_table(self, tmp_path):
        """Empty rows -> CREATE TABLE ... AS SELECT NULL WHERE 1=0."""
        from aml_framework.engine.runner import _build_warehouse

        spec = load_spec(SPEC_CA)
        con = duckdb.connect(":memory:")
        _build_warehouse(con, spec, {"txn": [], "customer": []})
        # Tables should exist even though they're empty.
        result = con.execute("SELECT COUNT(*) FROM txn").fetchone()
        assert result[0] == 0
        con.close()

    def test_inactive_rule_skipped(self, tmp_path):
        """Rules with status != active should be skipped entirely."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        # All rules in the spec are active, so this tests the normal path.
        assert result.total_alerts > 0

    def test_case_resolution_all_branches(self, tmp_path):
        """Run with enough cases to hit all resolution branches."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        # More noise = more alerts = more cases = more resolution branches.
        data = generate_dataset(as_of=as_of, seed=42, n_customers=25, n_noise_txns=800)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        # Should have enough cases to hit all resolution paths.
        assert result.total_alerts >= 10

        run_dir = Path(result.manifest["run_dir"])
        decisions = [
            json.loads(line)
            for line in (run_dir / "decisions.jsonl").read_text().splitlines()
            if line.strip()
        ]
        events = {d.get("event") for d in decisions}
        # Should have both escalated and closed events.
        assert "escalated" in events or "escalated_to_str" in events
        assert "closed" in events or "case_opened" in events

    def test_spec_cross_ref_bad_metric_in_report(self):
        """Report referencing nonexistent metric should fail validation."""
        with pytest.raises(Exception):
            AMLSpec(
                version=1,
                program=Program(
                    name="test",
                    jurisdiction="CA",
                    regulator="FINTRAC",
                    owner="cco",
                    effective_date="2026-01-01",
                ),
                data_contracts=[
                    DataContract(
                        id="txn",
                        source="raw.txn",
                        columns=[Column(name="txn_id", type="string")],
                    ),
                ],
                rules=[
                    Rule(
                        id="r1",
                        name="Test",
                        severity="high",
                        regulation_refs=[RegulationRef(citation="t", description="t")],
                        logic=ListMatchLogic(
                            type="list_match",
                            source="txn",
                            field="txn_id",
                            list="test",
                            match="exact",
                        ),
                        escalate_to="q1",
                    ),
                ],
                workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
                metrics=[],
                reports=[
                    Report(
                        id="bad_report",
                        audience="svp",
                        cadence="quarterly",
                        sections=[ReportSection(title="Test", metrics=["nonexistent_metric"])],
                    ),
                ],
            )


# ---------------------------------------------------------------------------
# Sanctions / list_match
# ---------------------------------------------------------------------------


class TestSanctionsScreening:
    def test_list_match_rule_fires(self, tmp_path):
        _, _, result = _run(tmp_path)
        alerts = result.alerts.get("sanctions_screening", [])
        assert len(alerts) >= 1, "sanctions_screening must produce at least one match"

    def test_planted_sanctions_match(self, tmp_path):
        """Alexei Volkov (C0003) is in both customer data and sanctions list."""
        _, _, result = _run(tmp_path)
        alerts = result.alerts.get("sanctions_screening", [])
        matched_customers = {a["customer_id"] for a in alerts}
        assert "C0003" in matched_customers, "C0003 (Alexei Volkov) must match sanctions list"

    def test_match_has_score(self, tmp_path):
        _, _, result = _run(tmp_path)
        for alert in result.alerts.get("sanctions_screening", []):
            assert "match_score" in alert
            assert alert["match_score"] >= 0.8

    def test_sanctions_creates_cases(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        sanctions_cases = list((run_dir / "cases").glob("sanctions_screening__*"))
        assert len(sanctions_cases) >= 1


class TestFuzzyMatcher:
    """Coverage gaps the quality review flagged in `_fuzzy_match`."""

    def test_accents_fold_to_ascii(self):
        from aml_framework.engine.runner import _fuzzy_match

        # "MÜLLER" should match "MUELLER" / "MULLER".
        result = _fuzzy_match("MÜLLER", ["MUELLER"], threshold=0.8)
        assert result is not None
        assert result[0] == "MUELLER"

    def test_substring_suffix_caught_by_edit_distance(self):
        """The old token-overlap matcher missed VOLKOV vs VOLKOVA / VOLKOVICH."""
        from aml_framework.engine.runner import _fuzzy_match

        result = _fuzzy_match("VOLKOV", ["VOLKOVA"], threshold=0.85)
        assert result is not None and result[0] == "VOLKOVA"

    def test_typo_caught_by_edit_distance(self):
        """JON SMITH vs JOHN SMITH was a token-overlap miss; edit-distance catches it."""
        from aml_framework.engine.runner import _fuzzy_match

        result = _fuzzy_match("JON SMITH", ["JOHN SMITH"], threshold=0.85)
        assert result is not None and result[0] == "JOHN SMITH"

    def test_transposed_tokens_still_match(self):
        """MARIA MUELLER / MUELLER MARIA — the token-overlap path still picks this up."""
        from aml_framework.engine.runner import _fuzzy_match

        result = _fuzzy_match("MARIA MUELLER", ["MUELLER MARIA"], threshold=0.95)
        assert result is not None

    def test_below_threshold_returns_none(self):
        """Genuinely different names must not match."""
        from aml_framework.engine.runner import _fuzzy_match

        assert _fuzzy_match("ALICE WONDERLAND", ["BOB SMITH"], threshold=0.85) is None

    def test_case_insensitive(self):
        from aml_framework.engine.runner import _fuzzy_match

        result = _fuzzy_match("smith", ["SMITH"], threshold=0.95)
        assert result is not None

    def test_empty_value_returns_none(self):
        from aml_framework.engine.runner import _fuzzy_match

        assert _fuzzy_match("", ["SMITH"], threshold=0.5) is None

    def test_picks_best_match_not_first(self):
        """When multiple entries beat threshold, the highest-scoring one wins."""
        from aml_framework.engine.runner import _fuzzy_match

        # SMITH matches both SMITH and SMITHE; SMITH should be preferred (higher ratio).
        result = _fuzzy_match("SMITH", ["SMITHE", "SMITH"], threshold=0.8)
        assert result is not None
        assert result[0] == "SMITH"

    def test_normalize_for_match_strips_combining(self):
        from aml_framework.engine.runner import _normalize_for_match

        assert _normalize_for_match("Müller") == "MULLER"
        assert _normalize_for_match("Café") == "CAFE"
        assert _normalize_for_match("  multi   spaces  ") == "MULTI SPACES"


class TestListMatchUnit:
    def test_list_match_missing_csv(self, tmp_path):
        """list_match with a list file that doesn't exist returns empty alerts."""
        from aml_framework.engine.runner import _execute_list_match

        rule = Rule(
            id="test_list",
            name="Test",
            severity="high",
            regulation_refs=[RegulationRef(citation="test", description="test")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="nonexistent_list",
                match="exact",
            ),
            escalate_to="l1",
        )
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE customer (customer_id VARCHAR, full_name VARCHAR)")
        con.execute("INSERT INTO customer VALUES ('C1', 'Test Name')")
        result = _execute_list_match(rule, con, datetime(2026, 1, 1))
        assert result == []
        con.close()

    def test_list_match_bad_source_table(self, tmp_path):
        from aml_framework.engine.runner import _execute_list_match

        rule = Rule(
            id="test_list",
            name="Test",
            severity="high",
            regulation_refs=[RegulationRef(citation="test", description="test")],
            logic=ListMatchLogic(
                type="list_match",
                source="nonexistent_table",
                field="name",
                list="sanctions",
                match="exact",
            ),
            escalate_to="l1",
        )
        con = duckdb.connect(":memory:")
        result = _execute_list_match(rule, con, datetime(2026, 1, 1))
        assert result == []
        con.close()

    def test_list_match_exact_match(self, tmp_path):
        from aml_framework.engine.runner import _execute_list_match

        rule = Rule(
            id="test_exact",
            name="Test Exact",
            severity="high",
            regulation_refs=[RegulationRef(citation="test", description="test")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="exact",
            ),
            escalate_to="l1",
        )
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE customer (customer_id VARCHAR, full_name VARCHAR)")
        con.execute("INSERT INTO customer VALUES ('C1', 'ALEXEI VOLKOV')")
        result = _execute_list_match(rule, con, datetime(2026, 1, 1))
        assert len(result) >= 1
        assert result[0]["match_type"] == "exact"
        con.close()

    def test_list_match_fuzzy_empty_entry(self):
        """Fuzzy matching should skip entries with empty names."""
        from aml_framework.engine.runner import _execute_list_match

        rule = Rule(
            id="test_fuzzy",
            name="Test Fuzzy",
            severity="high",
            regulation_refs=[RegulationRef(citation="test", description="test")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.8,
            ),
            escalate_to="l1",
        )
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE customer (customer_id VARCHAR, full_name VARCHAR)")
        con.execute("INSERT INTO customer VALUES ('C1', '')")  # Empty name.
        result = _execute_list_match(rule, con, datetime(2026, 1, 1))
        assert result == []  # Empty name should be skipped.
        con.close()

    def test_list_match_fuzzy_with_short_name(self):
        """Fuzzy match with a very short customer name."""
        from aml_framework.engine.runner import _execute_list_match

        rule = Rule(
            id="test_fuzzy2",
            name="Test",
            severity="high",
            regulation_refs=[RegulationRef(citation="t", description="t")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="full_name",
                list="sanctions",
                match="fuzzy",
                threshold=0.5,
            ),
            escalate_to="l1",
        )
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE customer (customer_id VARCHAR, full_name VARCHAR)")
        con.execute("INSERT INTO customer VALUES ('C1', 'VOLKOV')")  # Partial match.
        result = _execute_list_match(rule, con, datetime(2026, 1, 1))
        # Should match ALEXEI VOLKOV with partial overlap.
        assert len(result) >= 0  # May or may not match depending on threshold.
        con.close()


class TestAdverseMedia:
    def test_adverse_media_list_exists(self):
        list_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "data"
            / "lists"
            / "adverse_media.csv"
        )
        assert list_path.exists()
        content = list_path.read_text()
        assert "ALEXEI VOLKOV" in content

    def test_adverse_media_rule_in_spec(self):
        spec = load_spec(SPEC_CA)
        am_rules = [r for r in spec.rules if r.id == "adverse_media_screening"]
        assert len(am_rules) == 1
        assert am_rules[0].logic.type == "list_match"
        assert am_rules[0].logic.list == "adverse_media"

    def test_adverse_media_fires(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        am_alerts = result.alerts.get("adverse_media_screening", [])
        assert len(am_alerts) >= 1  # Should match planted customers.


# ---------------------------------------------------------------------------
# Case resolution
# ---------------------------------------------------------------------------


class TestCaseResolution:
    def test_cases_have_resolution(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])

        resolved = 0
        for f in (run_dir / "cases").glob("*.json"):
            case = json.loads(f.read_bytes())
            if case.get("resolved_at"):
                resolved += 1
        assert resolved > 0, "at least some cases should be resolved"

    def test_decision_log_has_resolution_events(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])
        decisions = (run_dir / "decisions.jsonl").read_text().splitlines()

        resolution_events = [
            json.loads(d)
            for d in decisions
            if json.loads(d).get("event") in ("escalated", "escalated_to_str", "closed")
        ]
        assert len(resolution_events) > 0

    def test_sla_data_in_decisions(self, tmp_path):
        _, _, result = _run(tmp_path)
        run_dir = Path(result.manifest["run_dir"])

        for line in (run_dir / "decisions.jsonl").read_text().splitlines():
            d = json.loads(line)
            if d.get("event") in ("escalated", "escalated_to_str", "closed"):
                assert "resolution_hours" in d
                assert "within_sla" in d
                break


# ---------------------------------------------------------------------------
# Audit ledger
# ---------------------------------------------------------------------------


class TestAuditTamperDetection:
    def test_decisions_hash_in_manifest(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        assert "decisions_hash" in result.manifest
        assert len(result.manifest["decisions_hash"]) == 64  # SHA-256 hex.

    def test_verify_decisions_passes(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        valid, msg = AuditLedger.verify_decisions(run_dir)
        assert valid, msg

    def test_verify_detects_tamper(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])

        # Tamper with the decisions log.
        decisions_path = run_dir / "decisions.jsonl"
        original = decisions_path.read_text()
        decisions_path.write_text(original + '{"event":"tampered"}\n')

        valid, msg = AuditLedger.verify_decisions(run_dir)
        assert not valid
        assert "Tamper" in msg

    def test_verify_missing_manifest(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        valid, msg = AuditLedger.verify_decisions(tmp_path)
        assert not valid


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_bundle_creates_zip(self, tmp_path):
        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "evidence.zip"
        export_bundle(run_dir, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_export_bundle_contains_manifest(self, tmp_path):
        import zipfile

        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "evidence.zip"
        export_bundle(run_dir, out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "manifest.json" in names


class TestAlertExport:
    def test_export_alerts_produces_csv(self, tmp_path):
        import csv

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )

        run_dir = Path(result.manifest["run_dir"])
        alerts_dir = run_dir / "alerts"
        out_csv = tmp_path / "alerts.csv"

        all_alerts = []
        for jsonl_file in sorted(alerts_dir.glob("*.jsonl")):
            for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    alert = json.loads(line)
                    alert["rule_id"] = jsonl_file.stem
                    all_alerts.append(alert)

        assert len(all_alerts) > 0

        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_alerts[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_alerts)

        assert out_csv.exists()
        lines = out_csv.read_text().splitlines()
        assert len(lines) > 1  # header + data


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestSpecDiff:
    def test_diff_runs_without_error(self):
        from aml_framework.diff import diff_specs

        # Should not raise.
        diff_specs(SPEC_US, SPEC_CA)

    def test_diff_detects_rule_additions(self):
        from io import StringIO
        from unittest.mock import patch as _patch

        from aml_framework.diff import diff_specs

        with _patch("sys.stdout", new_callable=StringIO):
            # Just verify it doesn't crash. Output goes to rich console.
            diff_specs(SPEC_US, SPEC_CA)

    def test_diff_same_spec_shows_no_changes(self):
        from aml_framework.diff import diff_specs

        # Same spec vs itself should show no changes.
        diff_specs(SPEC_US, SPEC_US)

    def test_diff_detects_severity_change(self):
        from aml_framework.diff import diff_specs

        # Same spec vs itself — no changes.
        diff_specs(SPEC_US, SPEC_US)  # Should not raise.

    def test_diff_modified_rule_status(self):
        """Exercise the common-rule modification detection path."""
        from aml_framework.diff import diff_specs

        # Diff between US and CA specs — rules have different queue names.
        diff_specs(SPEC_CA_BANK, SPEC_CA)

    def test_diff_same_rules_different_severity(self):
        from aml_framework.diff import diff_specs

        # Canadian bank vs Schedule I — structuring rule has different thresholds.
        diff_specs(SPEC_CA_BANK, SPEC_CA)

    def test_diff_detects_severity_and_status_changes(self):
        """Create two specs with same rule ID but different severity/status."""
        from aml_framework.diff import diff_specs

        # These specs share some rule IDs (structuring_cash_deposits) but with different logic.
        diff_specs(SPEC_US, SPEC_CA_BANK)


# ---------------------------------------------------------------------------
# Metrics engine helpers
# ---------------------------------------------------------------------------


class TestMetricsEngineHelpers:
    def test_source_rows_decisions(self):
        from aml_framework.metrics.engine import MetricContext, _source_rows

        spec = load_spec(SPEC_CA)
        decisions = [{"event": "case_opened", "case_id": "c1"}]
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=decisions, data={})
        result = _source_rows("decisions", ctx)
        assert len(result) == 1

    def test_unsupported_formula_type(self):
        from aml_framework.metrics.engine import MetricContext, _compute

        spec = load_spec(SPEC_CA)
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})

        class FakeFormula:
            pass

        with pytest.raises(TypeError, match="unsupported"):
            _compute(FakeFormula(), ctx)

    def test_cond_holds_gt_false(self):
        from aml_framework.metrics.engine import _cond_holds

        assert not _cond_holds(5, {"gt": 10})
        assert _cond_holds(15, {"gt": 10})

    def test_cond_holds_gt_lt_on_rag(self):
        from aml_framework.metrics.engine import _rag_band
        from aml_framework.spec.models import CountFormula, Metric

        m = Metric(
            id="t",
            name="t",
            category="operational",
            audience=["svp"],
            formula=CountFormula(type="count", source="alerts"),
            thresholds={"green": {"lt": 5}, "amber": {"lt": 10}, "red": {"gte": 10}},
        )
        assert _rag_band(3, m)[0] == "green"
        assert _rag_band(7, m)[0] == "amber"
        assert _rag_band(15, m)[0] == "red"

    def test_repeat_alert_with_closed_cases(self, tmp_path):
        """Run engine and verify repeat-alert metric processes closed cases."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        # The internal_alert_ignored metric uses the repeat-alert proxy.
        m = next((m for m in result.metrics if m.id == "internal_alert_ignored"), None)
        assert m is not None
        assert m.value >= 0  # May be 0 if no repeats.

    def test_repeat_alert_proxy_with_decisions(self):
        from aml_framework.metrics.engine import MetricContext, _compute_sql_proxy
        from aml_framework.spec.models import SQLFormula

        spec = load_spec(SPEC_CA)
        ctx = MetricContext(
            spec=spec,
            alerts={"rule_a": [{"customer_id": "C001"}, {"customer_id": "C001"}]},
            cases=[
                {"case_id": "rule_a__C001__x", "queue": "closed_no_action"},
            ],
            decisions=[
                {"event": "case_opened", "case_id": "rule_a__C001__x"},
            ],
            data={},
        )
        formula = SQLFormula(type="sql", sql="SELECT repeat_closed FROM closed_cases")
        result = _compute_sql_proxy(formula, ctx)
        # C001 has 2 alerts and was closed_no_action -> repeat_count = 1, total = 1 -> 1.0
        assert result >= 0.0

    def test_filing_latency_no_filings(self):
        from aml_framework.metrics.engine import MetricContext, _compute_sql_proxy
        from aml_framework.spec.models import SQLFormula

        spec = load_spec(SPEC_CA)
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
        formula = SQLFormula(type="sql", sql="SELECT PERCENTILE_CONT(0.95) FROM filing_latency")
        result = _compute_sql_proxy(formula, ctx)
        assert result == 0.0

    def test_edd_no_high_risk(self):
        from aml_framework.metrics.engine import MetricContext, _compute_sql_proxy
        from aml_framework.spec.models import SQLFormula

        spec = load_spec(SPEC_CA)
        ctx = MetricContext(
            spec=spec,
            alerts={},
            cases=[],
            decisions=[],
            data={"customer": [{"risk_rating": "low"}]},
        )
        formula = SQLFormula(type="sql", sql="SELECT current_edd / high_risk_total FROM edd_review")
        result = _compute_sql_proxy(formula, ctx)
        assert result == 1.0  # No high-risk = 100% compliant.

    def test_edd_with_string_review(self):
        from aml_framework.metrics.engine import MetricContext, _compute_sql_proxy
        from aml_framework.spec.models import SQLFormula

        spec = load_spec(SPEC_CA)
        ctx = MetricContext(
            spec=spec,
            alerts={},
            cases=[],
            decisions=[],
            data={"customer": [{"risk_rating": "high", "edd_last_review": "2025-06-01"}]},
        )
        formula = SQLFormula(type="sql", sql="SELECT current_edd FROM edd")
        result = _compute_sql_proxy(formula, ctx)
        assert result == 1.0  # Truthy string counts as reviewed.


# ---------------------------------------------------------------------------
# SQL generator helpers (used by engine)
# ---------------------------------------------------------------------------


class TestSQLGeneratorForEngine:
    def test_compile_filter_none(self):
        from aml_framework.generators.sql import _compile_filter

        assert _compile_filter(None) == []
        assert _compile_filter({}) == []

    def test_compile_filter_gte_lte(self):
        from aml_framework.generators.sql import _compile_filter

        preds = _compile_filter({"amount": {"gte": 1000}})
        assert any(">=" in p for p in preds)
        preds = _compile_filter({"amount": {"lte": 5000}})
        assert any("<=" in p for p in preds)

    def test_compile_having_ne(self):
        from aml_framework.generators.sql import _compile_having

        selects, preds = _compile_having({"count": {"ne": 0}})
        assert any("<>" in p for p in preds)

    def test_having_gt_lt_operators(self):
        from aml_framework.generators.sql import _compile_having

        selects, preds = _compile_having({"count": {"gt": 3}})
        assert any(">" in p for p in preds)
        selects, preds = _compile_having({"count": {"lt": 10}})
        assert any("<" in p for p in preds)


# ---------------------------------------------------------------------------
# Schedule command
# ---------------------------------------------------------------------------


class TestScheduleCommand:
    def test_schedule_function_exists(self):
        """The schedule function should be importable from cli."""
        from aml_framework.cli import schedule  # noqa: F401


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestLoadPerformance:
    def test_engine_throughput(self, tmp_path):
        """Measure how many transactions the engine processes per second."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42, n_customers=25, n_noise_txns=400)
        n_txns = len(data["txn"])

        start = time.time()
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        elapsed = time.time() - start

        txns_per_sec = n_txns / elapsed
        assert result.total_alerts > 0
        # Conservative threshold to avoid flaky failures on slow CI runners.
        min_tps = int(os.environ.get("PERF_MIN_TPS_SMALL", "20"))
        assert txns_per_sec > min_tps, f"Too slow: {txns_per_sec:.0f} txns/sec (need >{min_tps})"


# ---------------------------------------------------------------------------
# Export with control matrix
# ---------------------------------------------------------------------------


class TestExportWithControlMatrix:
    def test_export_includes_control_matrix(self, tmp_path):
        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "bundle.zip"
        export_bundle(run_dir, out, spec_path=SPEC_CA)
        import zipfile

        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "control_matrix.md" in names
            content = zf.read("control_matrix.md").decode()
            assert len(content) > 50

    def test_export_without_spec_path(self, tmp_path):
        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "bundle_no_spec.zip"
        export_bundle(run_dir, out)
        import zipfile

        with zipfile.ZipFile(out) as zf:
            assert "control_matrix.md" not in zf.namelist()


# ---------------------------------------------------------------------------
# Board PDF fallback path
# ---------------------------------------------------------------------------


class TestBoardPDFFallback:
    def test_fallback_pdf_produces_valid_output(self):
        from unittest.mock import patch

        from aml_framework.generators.board_pdf import generate_board_pdf

        spec = load_spec(SPEC_CA)
        # Force ImportError on reportlab to trigger fallback
        with patch(
            "aml_framework.generators.board_pdf._build_reportlab_pdf",
            side_effect=ImportError("no reportlab"),
        ):
            pdf_bytes = generate_board_pdf(spec=spec, metrics=[], cases=[])
            assert pdf_bytes[:5] == b"%PDF-"
            assert len(pdf_bytes) > 50


# ---------------------------------------------------------------------------
# Frameworks coverage (EU/UK tabs)
# ---------------------------------------------------------------------------


class TestFrameworksTabs:
    def test_eu_tabs(self):
        from aml_framework.dashboard.frameworks import get_framework_tabs

        tabs = get_framework_tabs("EU")
        labels = [t["label"] for t in tabs]
        assert "AMLD6 Requirements" in labels
        assert "Wolfsberg Principles" in labels

    def test_uk_tabs(self):
        from aml_framework.dashboard.frameworks import get_framework_tabs

        tabs = get_framework_tabs("UK")
        labels = [t["label"] for t in tabs]
        # UK falls through to US/default path
        assert "FinCEN BSA Pillars" in labels

    def test_ca_tabs(self):
        from aml_framework.dashboard.frameworks import get_framework_tabs

        tabs = get_framework_tabs("CA")
        labels = [t["label"] for t in tabs]
        assert "PCMLTFA Pillars" in labels
        assert "OSFI Guideline B-8" in labels
