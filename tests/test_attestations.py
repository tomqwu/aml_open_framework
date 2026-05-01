"""MLRO attestation workflow (PR-DATA-8).

Backs the "Data is the AML problem" whitepaper's DATA-8 claim that
"the MLRO's signature on a control attestation references a Manifest
version — by hash, unambiguous about what the program covered, when."
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aml_framework.attestations import (
    Attestation,
    AttestationLedger,
)


_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Attestation dataclass roundtrip
# ---------------------------------------------------------------------------


class TestAttestationDataclass:
    def test_roundtrip_to_dict_from_dict(self):
        a = Attestation(
            officer_id="MLRO-Smith",
            spec_content_hash="abc123" * 10,
            ts=_AS_OF,
            notes="annual sign-off",
        )
        b = Attestation.from_dict(a.to_dict())
        assert a == b

    def test_content_hash_stable_for_same_input(self):
        a = Attestation(
            officer_id="MLRO-Smith",
            spec_content_hash="abc",
            ts=_AS_OF,
            notes="",
        )
        assert a.content_hash() == a.content_hash()

    def test_content_hash_changes_with_officer(self):
        base = Attestation(officer_id="A", spec_content_hash="x", ts=_AS_OF)
        diff = Attestation(officer_id="B", spec_content_hash="x", ts=_AS_OF)
        assert base.content_hash() != diff.content_hash()


# ---------------------------------------------------------------------------
# AttestationLedger append + read + verify
# ---------------------------------------------------------------------------


class TestAttestationLedger:
    def test_empty_ledger(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        assert ledger.all() == []
        assert ledger.latest_for_spec("any-hash") is None
        ok, msg = ledger.verify()
        assert ok and "empty" in msg

    def test_append_then_read(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        a = ledger.append(
            officer_id="MLRO-Smith",
            spec_content_hash="hash-1",
            notes="initial",
        )
        all_records = ledger.all()
        assert len(all_records) == 1
        assert all_records[0].officer_id == "MLRO-Smith"
        assert all_records[0].spec_content_hash == "hash-1"
        # First entry has empty prev_hash (chain head).
        assert all_records[0].prev_hash == ""
        assert a.officer_id == "MLRO-Smith"

    def test_chain_links_prev_hashes(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        a1 = ledger.append(officer_id="O1", spec_content_hash="h1")
        a2 = ledger.append(officer_id="O2", spec_content_hash="h2")
        a3 = ledger.append(officer_id="O3", spec_content_hash="h3")
        records = ledger.all()
        assert records[1].prev_hash == a1.content_hash()
        assert records[2].prev_hash == a2.content_hash()
        assert a3.prev_hash == a2.content_hash()

    def test_verify_clean_chain(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        ledger.append(officer_id="O1", spec_content_hash="h1")
        ledger.append(officer_id="O2", spec_content_hash="h2")
        ok, msg = ledger.verify()
        assert ok
        assert "verified" in msg
        assert "2" in msg  # entry count

    def test_verify_detects_tampering_in_middle_entry(self, tmp_path: Path):
        # Tamper detection works for entries that have a *successor*
        # entry whose prev_hash pins them. Tampering with the most
        # recent entry isn't detectable by the chain alone — that's
        # the same caveat as the audit ledger's `verify_decisions`.
        ledger = AttestationLedger(dir=tmp_path)
        ledger.append(officer_id="O1", spec_content_hash="h1")
        ledger.append(officer_id="O2", spec_content_hash="h2")
        ledger.append(officer_id="O3", spec_content_hash="h3")
        # Tamper with the second (middle) entry; the third entry's
        # prev_hash now points at a content_hash the tampered entry
        # will not reproduce.
        lines = ledger.path.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[1])
        tampered["officer_id"] = "ATTACKER"
        lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, msg = ledger.verify()
        assert not ok
        assert "chain break" in msg

    def test_latest_for_spec(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        ledger.append(officer_id="O1", spec_content_hash="h1", ts=_AS_OF)
        ledger.append(
            officer_id="O2",
            spec_content_hash="h1",
            ts=_AS_OF + timedelta(days=1),
            notes="re-attested",
        )
        ledger.append(officer_id="O3", spec_content_hash="h2")
        # latest for h1 should be the second one
        latest = ledger.latest_for_spec("h1")
        assert latest is not None
        assert latest.officer_id == "O2"
        assert latest.notes == "re-attested"
        # latest for an unknown spec
        assert ledger.latest_for_spec("h-never-attested") is None

    def test_corrupt_lines_skipped(self, tmp_path: Path):
        ledger = AttestationLedger(dir=tmp_path)
        ledger.append(officer_id="O1", spec_content_hash="h1")
        # Manually append a malformed line.
        with ledger.path.open("a", encoding="utf-8") as f:
            f.write("not json\n")
        ledger.append(officer_id="O2", spec_content_hash="h2")
        # The healthy entries surface; the corrupt line is dropped.
        records = ledger.all()
        assert len(records) == 2
        assert records[0].officer_id == "O1"
        assert records[1].officer_id == "O2"


# ---------------------------------------------------------------------------
# CLI integration: aml run --strict gates on attestation
# ---------------------------------------------------------------------------


class TestStrictRunGate:
    def test_strict_run_refuses_unattested_spec(self, tmp_path: Path, monkeypatch):
        from typer.testing import CliRunner

        from aml_framework.cli import app

        # Use community_bank as the test spec; point attestations dir at
        # a fresh tmp_path so no prior attestations leak in.
        spec_path = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        monkeypatch.chdir(tmp_path)

        # Without --strict, run should succeed.
        runner = CliRunner()
        result_normal = runner.invoke(app, ["run", str(spec_path), "--seed", "42"])
        assert result_normal.exit_code == 0, result_normal.stdout

        # With --strict and no attestation, run should refuse.
        # (--attestations-dir defaults to ./.attestations, which we just
        # changed to via monkeypatch.chdir.)
        result_strict = runner.invoke(app, ["run", str(spec_path), "--strict"])
        assert result_strict.exit_code == 1
        assert "no attestation on file" in result_strict.stdout

    def test_strict_run_passes_after_attestation(self, tmp_path: Path, monkeypatch):
        from typer.testing import CliRunner

        from aml_framework.cli import app

        spec_path = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        # Record the attestation first.
        result_attest = runner.invoke(
            app,
            ["attest", str(spec_path), "--officer", "MLRO-Test"],
        )
        assert result_attest.exit_code == 0, result_attest.stdout
        assert "Attestation recorded" in result_attest.stdout

        # --strict should now pass.
        result_strict = runner.invoke(app, ["run", str(spec_path), "--strict"])
        assert result_strict.exit_code == 0, result_strict.stdout
        assert "--strict passed" in result_strict.stdout
        assert "MLRO-Test" in result_strict.stdout


# ---------------------------------------------------------------------------
# Aml attest CLI surface
# ---------------------------------------------------------------------------


class TestAttestCli:
    def test_attest_writes_ledger_entry(self, tmp_path: Path, monkeypatch):
        from typer.testing import CliRunner

        from aml_framework.cli import app

        spec_path = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "attest",
                str(spec_path),
                "--officer",
                "MLRO-Smith",
                "--notes",
                "annual review complete",
            ],
        )
        assert result.exit_code == 0, result.stdout
        # Default attestations dir is ./.attestations under cwd.
        ledger_path = tmp_path / ".attestations" / "attestations.jsonl"
        assert ledger_path.exists()
        line = ledger_path.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["officer_id"] == "MLRO-Smith"
        assert entry["notes"] == "annual review complete"
        assert entry["spec_content_hash"]  # whatever community_bank's hash is
        assert entry["prev_hash"] == ""  # first entry
