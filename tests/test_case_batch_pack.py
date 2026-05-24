"""PR-D4 — per-case / per-batch evidence pack tests (closes #377).

Granular complement to the whole-run audit pack (`test_audit_pack.py`).
Verifies the smaller per-case / batch ZIPs are well-formed, deterministic,
contain only the requested subset, fail loudly on missing cases, and
attach an HMAC signature when a key is supplied.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.generators.audit_pack import (
    CASE_PACK_VERSION,
    build_batch_pack,
    build_case_pack,
)
from aml_framework.spec import load_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_CA = PROJECT_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_case(
    run_dir: Path,
    case_id: str,
    *,
    rule_id: str = "structuring_cash",
    customer_id: str = "C0001",
    matched_rows: list[int] | None = None,
) -> Path:
    cases_dir = run_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    case = {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "severity": "high",
        "queue": "l1_aml_analyst",
        "alert": {
            "customer_id": customer_id,
            "sum_amount": 12000,
            "rule_id": rule_id,
            "rule_version": "abc1234567890def",
            "matched_row_ids": matched_rows or [1, 2, 3],
        },
        "evidence_requested": ["customer_kyc_profile"],
        "spec_program": "schedule_i_bank_aml",
        "input_hash": {
            "txn": {
                "row_count": 1311,
                "content_hash": "a" * 64,
                "source_path": "data/input/txn.csv",
                "schema_hash": "deadbeef0badcafe",
            }
        },
        "status": "open",
    }
    path = cases_dir / f"{case_id}.json"
    path.write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_decisions(run_dir: Path, events: list[dict[str, Any]]) -> None:
    (run_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n",
        encoding="utf-8",
    )


def _write_alert(
    run_dir: Path,
    rule_id: str,
    rows: list[dict[str, Any]],
) -> None:
    alerts_dir = run_dir / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    (alerts_dir / f"{rule_id}.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
        encoding="utf-8",
    )


def _write_rule_sql(run_dir: Path, rule_id: str, sql: str = "-- demo SQL\n") -> None:
    rules_dir = run_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / f"{rule_id}.sql").write_text(sql, encoding="utf-8")


def _write_spec_snapshot(run_dir: Path, body: str = "# spec snapshot\n") -> None:
    (run_dir / "spec_snapshot.yaml").write_text(body, encoding="utf-8")


@pytest.fixture()
def populated_run(tmp_path: Path) -> Path:
    """Single-rule run_dir with three cases + a few decisions + alerts."""
    run = tmp_path / "run-test"
    run.mkdir()
    _write_case(run, "case-001", customer_id="C0001", matched_rows=[10])
    _write_case(run, "case-002", customer_id="C0002", matched_rows=[20])
    _write_case(run, "case-003", rule_id="rapid_movement", customer_id="C0003", matched_rows=[30])
    _write_decisions(
        run,
        [
            {"case_id": "case-001", "event": "case_opened"},
            {"case_id": "case-001", "event": "str_filed"},
            {"case_id": "case-002", "event": "closed_no_action"},
            {"case_id": "case-003", "event": "case_opened"},
        ],
    )
    _write_alert(
        run,
        "structuring_cash",
        [
            {"customer_id": "C0001", "matched_row_ids": [10], "rule_id": "structuring_cash"},
            {"customer_id": "C0002", "matched_row_ids": [20], "rule_id": "structuring_cash"},
        ],
    )
    _write_alert(
        run,
        "rapid_movement",
        [{"customer_id": "C0003", "matched_row_ids": [30], "rule_id": "rapid_movement"}],
    )
    _write_rule_sql(run, "structuring_cash", "SELECT 1 -- structuring\n")
    _write_rule_sql(run, "rapid_movement", "SELECT 1 -- rapid\n")
    _write_spec_snapshot(run, "# bank spec\n")
    return run


# ---------------------------------------------------------------------------
# build_case_pack — single-case pack
# ---------------------------------------------------------------------------


class TestCasePack:
    def test_returns_valid_zip(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            assert zf.testzip() is None

    def test_contains_case_decisions_alerts_lineage_rulesql_and_manifest(
        self, populated_run: Path
    ) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        assert "cases/case-001.json" in names
        assert "decisions/case-001.jsonl" in names
        assert "alerts/case-001.jsonl" in names
        assert "lineage/case-001.json" in names
        assert "rules/structuring_cash.sql" in names
        assert "spec_snapshot.yaml" in names
        assert "program.md" in names
        assert "manifest.json" in names

    def test_decisions_subchain_filtered_to_case(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            body = zf.read("decisions/case-001.jsonl").decode("utf-8")
        lines = [json.loads(line) for line in body.splitlines() if line.strip()]
        # case-001 has 2 events; case-002 / case-003 must not leak in.
        assert {evt["event"] for evt in lines} == {"case_opened", "str_filed"}
        assert all(evt["case_id"] == "case-001" for evt in lines)

    def test_alert_payload_restricted_to_case_rows(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            body = zf.read("alerts/case-001.jsonl").decode("utf-8")
        rows = [json.loads(line) for line in body.splitlines() if line.strip()]
        # Only the row whose matched_row_ids match case-001's [10] survives.
        assert len(rows) == 1
        assert rows[0]["matched_row_ids"] == [10]
        assert rows[0]["customer_id"] == "C0001"

    def test_alert_filter_excludes_other_cases_sharing_matched_rows(self, tmp_path: Path) -> None:
        """Codex P2 regression: network/graph-pattern rules emit per-seed
        alerts that share a subgraph's row set, so two cases can have
        identical ``matched_row_ids`` for different customers. The filter
        must match on (customer_id, matched_row_ids) together, not on
        matched_row_ids alone."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-network"
        run.mkdir()
        # Two cases share matched_row_ids but seed different customers
        # (typical of a network_pattern rule).
        _write_case(
            run, "case-net-X", rule_id="rapid_movement", customer_id="C0007", matched_rows=[1, 2]
        )
        _write_case(
            run, "case-net-Y", rule_id="rapid_movement", customer_id="C0008", matched_rows=[1, 2]
        )
        _write_decisions(run, [])
        _write_alert(
            run,
            "rapid_movement",
            [
                {"customer_id": "C0007", "matched_row_ids": [1, 2], "rule_id": "rapid_movement"},
                {"customer_id": "C0008", "matched_row_ids": [1, 2], "rule_id": "rapid_movement"},
            ],
        )
        payload = build_case_pack(spec, run / "cases" / "case-net-X.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            body = zf.read("alerts/case-net-X.jsonl").decode("utf-8")
        rows = [json.loads(line) for line in body.splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["customer_id"] == "C0007"
        # The C0008 sibling alert must NOT leak in despite same matched rows.
        assert all(r["customer_id"] != "C0008" for r in rows)

    def test_alert_payload_is_case_canonical_alert_only(self, tmp_path: Path) -> None:
        """Codex P2 (custom_sql case): two alerts sharing customer_id +
        matched_row_ids but differing on other fields (e.g. window_end)
        produce distinct case_ids. The case pack must ship only the
        canonical alert from the requested case, never the sibling.
        Our implementation derives the alert from ``case["alert"]`` so
        this is guaranteed by construction — pinning it here so a
        future refactor can't regress."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-cs"
        run.mkdir()
        cases_dir = run / "cases"
        cases_dir.mkdir()
        # Two cases share customer + matched_rows but have different
        # window_end (typical of a custom_sql rule firing twice).
        for cid, w_end in (("case-W1", "2026-04-01"), ("case-W2", "2026-04-15")):
            case = {
                "case_id": cid,
                "rule_id": "custom_dual",
                "rule_name": "Custom dual fire",
                "severity": "high",
                "queue": "l1_aml_analyst",
                "alert": {
                    "customer_id": "C0099",
                    "matched_row_ids": [7, 8],
                    "window_end": w_end,
                },
                "evidence_requested": [],
                "spec_program": "schedule_i_bank_aml",
                "input_hash": {},
                "status": "open",
            }
            (cases_dir / f"{cid}.json").write_text(
                json.dumps(case, indent=2, sort_keys=True), encoding="utf-8"
            )
        _write_decisions(run, [])
        payload = build_case_pack(spec, run / "cases" / "case-W1.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            body = zf.read("alerts/case-W1.jsonl").decode("utf-8")
        rows = [json.loads(line) for line in body.splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["window_end"] == "2026-04-01"
        # The W2 sibling alert must NOT leak in.
        assert all(r["window_end"] != "2026-04-15" for r in rows)

    def test_pii_masking_applied_to_case_pack(self, tmp_path: Path) -> None:
        """Codex P1: when the run was produced with AML_PII_MASKING=1
        the case file still carries plaintext PII (the engine masks
        alerts/<rule>.jsonl but writes the case dict raw). The case
        pack must re-apply the run's pii_map so plaintext never leaks
        into a pack intended for external sharing."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-masked"
        run.mkdir()
        _write_case(run, "case-mask", customer_id="C0001", matched_rows=[10])
        _write_decisions(
            run,
            [
                {"case_id": "case-mask", "event": "case_opened", "customer_id": "C0001"},
            ],
        )
        # Write the masking sidecar that AuditLedger._mask_alert produces.
        (run / "pii_map.jsonl").write_text(
            json.dumps({"field": "customer_id", "hash": "deadbeefcafe1234", "plaintext": "C0001"})
            + "\n",
            encoding="utf-8",
        )
        payload = build_case_pack(spec, run / "cases" / "case-mask.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            case_doc = json.loads(zf.read("cases/case-mask.json"))
            alert_body = zf.read("alerts/case-mask.jsonl").decode("utf-8")
            decision_body = zf.read("decisions/case-mask.jsonl").decode("utf-8")
            manifest = json.loads(zf.read("manifest.json"))
        # Every surface that carried plaintext "C0001" must now carry the hash.
        assert case_doc["alert"]["customer_id"] == "deadbeefcafe1234"
        assert "C0001" not in alert_body
        assert "deadbeefcafe1234" in alert_body
        assert "C0001" not in decision_body
        assert manifest["pii_masked"] is True

    def test_pii_masking_replaces_plaintext_in_compound_case_id(self, tmp_path: Path) -> None:
        """Codex P1 follow-up: the engine's case_id is a compound
        ``<rule>__<customer>__<ts>`` string. Substring masking must
        replace the embedded plaintext PII inside identifiers
        everywhere (ZIP entry names, manifest case_id, lineage)."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-compound"
        run.mkdir()
        # Hand-craft a case with engine-shaped compound case_id.
        cases_dir = run / "cases"
        cases_dir.mkdir()
        raw_case_id = "structuring_cash__C0001__2026-04-23T120000"
        masked_customer = "abcd1234abcd1234"
        case = {
            "case_id": raw_case_id,
            "rule_id": "structuring_cash",
            "rule_name": "Structuring",
            "severity": "high",
            "queue": "l1_aml_analyst",
            "alert": {"customer_id": "C0001", "matched_row_ids": [10]},
            "evidence_requested": [],
            "spec_program": "schedule_i_bank_aml",
            "input_hash": {},
            "status": "open",
        }
        (cases_dir / f"{raw_case_id}.json").write_text(
            json.dumps(case, indent=2, sort_keys=True), encoding="utf-8"
        )
        _write_decisions(
            run,
            [{"case_id": raw_case_id, "event": "case_opened", "customer_id": "C0001"}],
        )
        (run / "pii_map.jsonl").write_text(
            json.dumps({"field": "customer_id", "hash": masked_customer, "plaintext": "C0001"})
            + "\n",
            encoding="utf-8",
        )
        payload = build_case_pack(spec, cases_dir / f"{raw_case_id}.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
        # No ZIP entry name carries plaintext "C0001".
        assert not any("C0001" in n for n in names), names
        # The masked compound id appears in entry names.
        masked_id = f"structuring_cash__{masked_customer}__2026-04-23T120000"
        assert f"cases/{masked_id}.json" in names
        assert f"lineage/{masked_id}.json" in names
        # Manifest carries the masked case_id, not the plaintext.
        assert manifest["case_id"] == masked_id
        assert "C0001" not in json.dumps(manifest)

    def test_no_pii_map_sidecar_means_no_masking(self, populated_run: Path) -> None:
        """The reverse contract: unmasked runs are a pure no-op — the
        case dict is shipped as-is and `pii_masked` is False."""
        spec = load_spec(SPEC_CA)
        # populated_run has no pii_map.jsonl
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            case_doc = json.loads(zf.read("cases/case-001.json"))
            manifest = json.loads(zf.read("manifest.json"))
        assert case_doc["alert"]["customer_id"] == "C0001"
        assert manifest["pii_masked"] is False

    def test_alert_filter_excludes_other_same_customer_alerts(self, tmp_path: Path) -> None:
        """Codex P2 regression: when one customer trips a rule multiple
        times, each alert maps to a separate case. The case pack must
        ship only the requested case's evidence — same-customer alerts
        belonging to *other* cases must NOT leak in."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-sibling"
        run.mkdir()
        # Two cases for the same customer, different matched_row_ids.
        _write_case(run, "case-A", customer_id="C0042", matched_rows=[100])
        _write_case(run, "case-B", customer_id="C0042", matched_rows=[200])
        _write_decisions(run, [])
        _write_alert(
            run,
            "structuring_cash",
            [
                {"customer_id": "C0042", "matched_row_ids": [100], "rule_id": "structuring_cash"},
                {"customer_id": "C0042", "matched_row_ids": [200], "rule_id": "structuring_cash"},
            ],
        )
        payload = build_case_pack(spec, run / "cases" / "case-A.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            body = zf.read("alerts/case-A.jsonl").decode("utf-8")
        rows = [json.loads(line) for line in body.splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["matched_row_ids"] == [100]
        # The sibling row with [200] must not leak in.
        assert all(r["matched_row_ids"] != [200] for r in rows)

    def test_lineage_carries_rule_version_and_input_files(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            lineage = json.loads(zf.read("lineage/case-001.json"))
        assert lineage["rule_id"] == "structuring_cash"
        assert lineage["rule_version"] == "abc1234567890def"
        assert lineage["matched_row_ids"] == [10]
        assert lineage["input_files"][0]["source_path"] == "data/input/txn.csv"
        assert lineage["input_files"][0]["schema_hash"] == "deadbeef0badcafe"

    def test_lineage_rule_version_falls_back_to_decisions(self, tmp_path: Path) -> None:
        """Codex P2 regression: the engine stamps `rule_version` on the
        `case_opened` decision event, not on the alert object. Packs
        built from real `aml run` output must derive rule_version from
        the decision sub-chain when the alert payload omits it."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-decver"
        run.mkdir()
        cases_dir = run / "cases"
        cases_dir.mkdir()
        # Hand-crafted case dict whose alert has NO rule_version (mirrors
        # the engine's normal output shape).
        case = {
            "case_id": "case-engine-001",
            "rule_id": "structuring_cash",
            "rule_name": "Structuring",
            "severity": "high",
            "queue": "l1_aml_analyst",
            "alert": {"customer_id": "C0001", "matched_row_ids": [42]},
            "evidence_requested": [],
            "spec_program": "schedule_i_bank_aml",
            "input_hash": {},
            "status": "open",
        }
        (cases_dir / "case-engine-001.json").write_text(
            json.dumps(case, indent=2, sort_keys=True), encoding="utf-8"
        )
        _write_decisions(
            run,
            [
                {
                    "case_id": "case-engine-001",
                    "event": "case_opened",
                    "rule_id": "structuring_cash",
                    "rule_version": "6b572889743ea02e",
                },
            ],
        )
        payload = build_case_pack(spec, run / "cases" / "case-engine-001.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            lineage = json.loads(zf.read("lineage/case-engine-001.json"))
        assert lineage["rule_version"] == "6b572889743ea02e"

    def test_manifest_records_kind_and_case_id(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["pack_version"] == CASE_PACK_VERSION
        assert manifest["pack_kind"] == "case"
        assert manifest["case_id"] == "case-001"
        assert manifest["rule_id"] == "structuring_cash"
        # Per-file hashes match the archive.
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for path, claimed in manifest["files"].items():
                actual = hashlib.sha256(zf.read(path)).hexdigest()
                assert actual == claimed, f"hash mismatch on {path}"

    def test_deterministic_same_input_same_bytes(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        a = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        b = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        assert a == b

    def test_missing_case_raises_file_not_found(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        with pytest.raises(FileNotFoundError, match="case file not found"):
            build_case_pack(spec, populated_run / "cases" / "does-not-exist.json", populated_run)

    def test_signing_key_attaches_hmac_signature(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        key = "secret-key-from-vault"
        payload = build_case_pack(
            spec,
            populated_run / "cases" / "case-001.json",
            populated_run,
            signing_key=key,
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["signature"]["algorithm"] == "HMAC-SHA256"
        expected = hmac.new(
            key.encode("utf-8"), manifest["bundle_hash"].encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert manifest["signature"]["value"] == expected

    def test_no_signing_key_means_no_signature_field(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_case_pack(spec, populated_run / "cases" / "case-001.json", populated_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert "signature" not in manifest

    def test_missing_rule_sql_omitted_gracefully(self, tmp_path: Path) -> None:
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-nosql"
        run.mkdir()
        _write_case(run, "case-x", customer_id="C0001", matched_rows=[1])
        _write_decisions(run, [])
        payload = build_case_pack(spec, run / "cases" / "case-x.json", run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        # No rules/<rule>.sql since we didn't write one — but still a valid pack.
        assert not any(n.startswith("rules/") for n in names)
        assert "cases/case-x.json" in names


# ---------------------------------------------------------------------------
# build_batch_pack — multi-case pack
# ---------------------------------------------------------------------------


class TestBatchPack:
    def test_returns_valid_zip_with_each_case_entry(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_batch_pack(spec, populated_run, ["case-001", "case-003"])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            assert zf.testzip() is None
            names = set(zf.namelist())
        assert "cases/case-001.json" in names
        assert "cases/case-003.json" in names
        # case-002 was not requested → must NOT appear.
        assert "cases/case-002.json" not in names
        assert "decisions/case-002.jsonl" not in names

    def test_batch_summary_records_requested_ids(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_batch_pack(spec, populated_run, ["case-003", "case-001"])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            summary = json.loads(zf.read("batch_summary.json"))
            manifest = json.loads(zf.read("manifest.json"))
        assert summary["case_count"] == 2
        assert summary["case_ids"] == ["case-001", "case-003"]
        assert set(summary["rules"]) == {"structuring_cash", "rapid_movement"}
        assert manifest["pack_kind"] == "batch"
        assert manifest["case_count"] == 2

    def test_deterministic_independent_of_case_id_order(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        a = build_batch_pack(spec, populated_run, ["case-001", "case-003"])
        b = build_batch_pack(spec, populated_run, ["case-003", "case-001"])
        # Order normalised internally (dedup keeps first-seen; manifest sorts).
        # The two packs should hash identically because every per-case file
        # path keys off case_id and the manifest stores sorted ids.
        with zipfile.ZipFile(io.BytesIO(a)) as za, zipfile.ZipFile(io.BytesIO(b)) as zb:
            assert sorted(za.namelist()) == sorted(zb.namelist())
            for name in za.namelist():
                if name == "manifest.json":
                    # Manifest's "files" hashes must agree even if outer bytes differ.
                    ma = json.loads(za.read(name))
                    mb = json.loads(zb.read(name))
                    assert ma["files"] == mb["files"]
                    assert ma["bundle_hash"] == mb["bundle_hash"]
                else:
                    assert za.read(name) == zb.read(name)

    def test_missing_case_raises_file_not_found(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        with pytest.raises(FileNotFoundError):
            build_batch_pack(spec, populated_run, ["case-001", "case-ghost"])

    def test_empty_case_ids_rejected(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        with pytest.raises(ValueError, match="case_ids must not be empty"):
            build_batch_pack(spec, populated_run, [])

    def test_signing_key_signs_batch_manifest(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        key = "batch-secret"
        payload = build_batch_pack(spec, populated_run, ["case-001", "case-002"], signing_key=key)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        expected = hmac.new(
            key.encode("utf-8"), manifest["bundle_hash"].encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert manifest["signature"]["value"] == expected

    def test_batch_pack_masks_compound_case_ids_in_summary(self, tmp_path: Path) -> None:
        """Batch summary + manifest must carry masked case_ids when the
        run is masked (Codex P1)."""
        spec = load_spec(SPEC_CA)
        run = tmp_path / "run-batch-mask"
        run.mkdir()
        cases_dir = run / "cases"
        cases_dir.mkdir()
        ids = ["structuring_cash__C0001__t1", "structuring_cash__C0002__t2"]
        for cid, cust in zip(ids, ("C0001", "C0002"), strict=True):
            case = {
                "case_id": cid,
                "rule_id": "structuring_cash",
                "rule_name": "S",
                "severity": "high",
                "queue": "q",
                "alert": {"customer_id": cust, "matched_row_ids": [1]},
                "evidence_requested": [],
                "spec_program": "schedule_i_bank_aml",
                "input_hash": {},
                "status": "open",
            }
            (cases_dir / f"{cid}.json").write_text(
                json.dumps(case, indent=2, sort_keys=True), encoding="utf-8"
            )
        _write_decisions(run, [])
        (run / "pii_map.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {"field": "customer_id", "hash": "h1h1h1h1h1h1h1h1", "plaintext": "C0001"}
                    ),
                    json.dumps(
                        {"field": "customer_id", "hash": "h2h2h2h2h2h2h2h2", "plaintext": "C0002"}
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        payload = build_batch_pack(spec, run, ids)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            summary = json.loads(zf.read("batch_summary.json"))
            manifest = json.loads(zf.read("manifest.json"))
            names = set(zf.namelist())
        assert manifest["pii_masked"] is True
        assert all("C000" not in cid for cid in summary["case_ids"])
        assert all("C000" not in cid for cid in manifest["case_ids"])
        assert not any("C000" in n for n in names)

    def test_duplicate_case_ids_deduplicated(self, populated_run: Path) -> None:
        spec = load_spec(SPEC_CA)
        payload = build_batch_pack(spec, populated_run, ["case-001", "case-001"])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            summary = json.loads(zf.read("batch_summary.json"))
        assert summary["case_count"] == 1
        assert summary["case_ids"] == ["case-001"]


# ---------------------------------------------------------------------------
# CLI hooks
# ---------------------------------------------------------------------------


class TestCli:
    def test_export_case_writes_zip(self, populated_run: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        out = tmp_path / "single.zip"
        result = runner.invoke(
            app,
            [
                "export-case",
                str(SPEC_CA),
                str(populated_run),
                "case-001",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists() and out.stat().st_size > 0
        with zipfile.ZipFile(out) as zf:
            assert "cases/case-001.json" in zf.namelist()

    def test_export_case_missing_case_exits_nonzero(
        self, populated_run: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "export-case",
                str(SPEC_CA),
                str(populated_run),
                "case-ghost",
                "--out",
                str(tmp_path / "missing.zip"),
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_export_batch_writes_zip(self, populated_run: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        out = tmp_path / "batch.zip"
        result = runner.invoke(
            app,
            [
                "export-batch",
                str(SPEC_CA),
                str(populated_run),
                "--cases",
                "case-001,case-003",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        assert "cases/case-001.json" in names
        assert "cases/case-003.json" in names
        assert "batch_summary.json" in names

    def test_export_batch_empty_cases_flag_rejected(
        self, populated_run: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "export-batch",
                str(SPEC_CA),
                str(populated_run),
                "--cases",
                ",",
                "--out",
                str(tmp_path / "empty.zip"),
            ],
        )
        assert result.exit_code != 0
        assert "at least one case_id" in result.output.lower()

    def test_export_batch_missing_case_exits_nonzero(
        self, populated_run: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "export-batch",
                str(SPEC_CA),
                str(populated_run),
                "--cases",
                "case-001,case-ghost",
                "--out",
                str(tmp_path / "missing.zip"),
            ],
        )
        assert result.exit_code != 0
        assert "case file not found" in result.output.lower()
