"""Per-decision audit metadata + lineage walk-back (PR-DATA-4).

Backs the "Data is the AML problem" whitepaper's DATA-4 claim that a
2LoD reviewer can walk back from any KPI / case_id to the producing
run, rule_version, spec hash, and input file hashes — without manually
stitching artifacts.

The PR adds three pieces:
1. `schema_version` stamped on every decision event written by
   `AuditLedger.append_decision`.
2. `rule_version_hash(rule)` — a stable SHA-256[:16] over a rule's
   serialised content, stamped onto `case_opened` events so the
   lineage chain survives spec edits.
3. `walk_lineage(run_dir, case_id)` — pure helper that reconstructs
   the full chain from a run dir's artifacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aml_framework.data.synthetic import generate_dataset
from aml_framework.engine.audit import (
    DECISION_SCHEMA_VERSION,
    rule_version_hash,
    walk_lineage,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.loader import load_spec

_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)
_COMMUNITY_BANK = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _read_decisions(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Schema version + decision metadata stamping
# ---------------------------------------------------------------------------


class TestDecisionSchemaVersion:
    def test_every_event_carries_schema_version(self, tmp_path: Path):
        spec = load_spec(_COMMUNITY_BANK)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=_COMMUNITY_BANK,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions = _read_decisions(run_dirs[-1])
        assert decisions, "expected at least one decision event"
        for ev in decisions:
            assert ev.get("schema_version") == DECISION_SCHEMA_VERSION, (
                f"event missing schema_version: {ev}"
            )

    def test_schema_version_is_stable_constant(self):
        # Bumping this requires reader-side migration logic in
        # `walk_lineage` and any external tooling that reads the ledger.
        assert DECISION_SCHEMA_VERSION == 2


# ---------------------------------------------------------------------------
# rule_version_hash
# ---------------------------------------------------------------------------


class TestRuleVersionHash:
    def test_same_rule_same_hash(self):
        spec = load_spec(_COMMUNITY_BANK)
        rule = spec.rules[0]
        assert rule_version_hash(rule) == rule_version_hash(rule)

    def test_different_rules_different_hashes(self):
        spec = load_spec(_COMMUNITY_BANK)
        # community_bank has multiple rules; their hashes must differ.
        h1 = rule_version_hash(spec.rules[0])
        h2 = rule_version_hash(spec.rules[1])
        assert h1 != h2

    def test_hash_is_16_hex_chars(self):
        spec = load_spec(_COMMUNITY_BANK)
        h = rule_version_hash(spec.rules[0])
        assert len(h) == 16
        int(h, 16)  # raises if not hex

    def test_dict_input_supported(self):
        # Test the fallback path for callers without a Pydantic model.
        h = rule_version_hash({"id": "r1", "threshold": 100})
        assert len(h) == 16


# ---------------------------------------------------------------------------
# rule_version stamped on case_opened events
# ---------------------------------------------------------------------------


class TestCaseOpenedCarriesRuleVersion:
    def test_every_case_opened_has_rule_version(self, tmp_path: Path):
        spec = load_spec(_COMMUNITY_BANK)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=_COMMUNITY_BANK,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions = _read_decisions(run_dirs[-1])
        case_opened = [d for d in decisions if d.get("event") == "case_opened"]
        assert case_opened, "community_bank should produce at least one alert/case"
        for ev in case_opened:
            assert ev.get("rule_version"), f"case_opened missing rule_version: {ev}"
            assert len(ev["rule_version"]) == 16

    def test_rule_version_consistent_per_rule(self, tmp_path: Path):
        spec = load_spec(_COMMUNITY_BANK)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=_COMMUNITY_BANK,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions = _read_decisions(run_dirs[-1])
        # All case_opened events for the same rule_id must carry the
        # same rule_version (rule didn't change mid-run).
        by_rule: dict[str, set[str]] = {}
        for d in decisions:
            if d.get("event") == "case_opened":
                by_rule.setdefault(d["rule_id"], set()).add(d["rule_version"])
        for rule_id, versions in by_rule.items():
            assert len(versions) == 1, (
                f"rule {rule_id} produced multiple rule_versions in one run: {versions}"
            )


# ---------------------------------------------------------------------------
# walk_lineage helper
# ---------------------------------------------------------------------------


class TestWalkLineage:
    def test_walk_returns_full_chain(self, tmp_path: Path):
        spec = load_spec(_COMMUNITY_BANK)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=_COMMUNITY_BANK,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        # finalize() writes the manifest; call it so walk_lineage can read it.
        # (run_spec already writes the manifest at the end of its loop;
        # if not, the test should still see the case file + decisions.)
        case_id = result.case_ids[0]

        chain = walk_lineage(run_dir, case_id)
        assert chain["case_id"] == case_id
        assert chain["case"] is not None
        assert chain["rule_id"]
        assert chain["rule_version"], "lineage should carry rule_version from case_opened"
        assert chain["queue"]
        assert chain["spec_content_hash"]
        # input_files should be populated from input_manifest.json
        assert chain["input_files"], "input manifest should list contract hashes"
        # decisions list should include at least the case_opened event
        case_open_events = [d for d in chain["decisions"] if d["event"] == "case_opened"]
        assert case_open_events, "expected case_opened decision in chain"

    def test_unknown_case_returns_empty_chain(self, tmp_path: Path):
        spec = load_spec(_COMMUNITY_BANK)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=_COMMUNITY_BANK,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        chain = walk_lineage(run_dir, "C-DOES-NOT-EXIST")
        assert chain["case"] is None
        assert chain["rule_id"] is None
        # Non-case-specific anchors should still be present
        assert chain["spec_content_hash"]

    def test_legacy_run_dir_without_rule_version_does_not_crash(self, tmp_path: Path):
        """Old runs predating PR-DATA-4 don't have rule_version on
        case_opened events. walk_lineage must surface what's available
        rather than crash."""
        # Hand-craft a minimal run dir mimicking pre-PR-DATA-4 shape.
        rd = tmp_path / "run-legacy"
        (rd / "cases").mkdir(parents=True)
        (rd / "cases" / "C-LEGACY.json").write_text(
            json.dumps({"case_id": "C-LEGACY", "rule_id": "r_old", "queue": "L1"})
        )
        # decisions.jsonl with a case_opened event missing rule_version
        # AND missing schema_version (a true legacy run).
        (rd / "decisions.jsonl").write_text(
            json.dumps({"event": "case_opened", "case_id": "C-LEGACY", "rule_id": "r_old"}) + "\n"
        )
        chain = walk_lineage(rd, "C-LEGACY")
        assert chain["case_id"] == "C-LEGACY"
        assert chain["rule_id"] == "r_old"
        assert chain["rule_version"] is None  # gracefully None, not crash
