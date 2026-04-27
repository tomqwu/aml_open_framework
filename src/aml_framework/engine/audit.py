"""Append-only audit ledger.

Writes artifacts under a run directory:
    <artifacts>/run-<timestamp>/
        manifest.json
        spec_snapshot.yaml
        input_manifest.json
        rules/<rule_id>.sql
        alerts/<rule_id>.jsonl
        alerts/<rule_id>.hash
        cases/<case_id>.json
        decisions.jsonl

Hashes are SHA-256 over canonicalised bytes. Engine-time decisions stamp `ts`
from `as_of` so that a re-run with the same spec, data, and `as_of` produces
the same `decisions_hash` — that's the contract `test_run_is_reproducible`
verifies. Human decisions appended later (via `append_to_run_dir`) use a real
wall-clock `ts` and are not part of the reproducibility contract.

Tamper detection caveat: `verify_decisions` reads the expected hash from
`manifest.json` in the same run directory. An attacker who can rewrite
`decisions.jsonl` can also rewrite `manifest.json`. For real assurance,
external callers should pass `expected_hash=...` from an out-of-band store
(database row, signed log, WORM bucket).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aml_framework import __version__ as ENGINE_VERSION


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class AuditLedger:
    run_dir: Path
    spec_path: Path
    spec_content_hash: str
    as_of: datetime
    input_manifest: dict[str, Any] = field(default_factory=dict)
    rule_outputs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls, artifacts_root: Path, spec_path: Path, spec_hash: str, as_of: datetime
    ) -> "AuditLedger":
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = artifacts_root / f"run-{ts}"
        (run_dir / "rules").mkdir(parents=True, exist_ok=True)
        (run_dir / "alerts").mkdir(parents=True, exist_ok=True)
        (run_dir / "cases").mkdir(parents=True, exist_ok=True)

        shutil.copyfile(spec_path, run_dir / "spec_snapshot.yaml")

        ledger = cls(
            run_dir=run_dir,
            spec_path=spec_path,
            spec_content_hash=spec_hash,
            as_of=as_of,
        )
        (run_dir / "decisions.jsonl").touch()
        return ledger

    def record_input(self, contract_id: str, rows: list[dict[str, Any]]) -> None:
        ordered = sorted(rows, key=lambda r: _canonical_json(r))
        digest = _sha256(b"\n".join(_canonical_json(r) for r in ordered))
        timestamps = [r.get("booked_at") for r in rows if r.get("booked_at") is not None]
        self.input_manifest[contract_id] = {
            "row_count": len(rows),
            "content_hash": digest,
            "earliest_ts": str(min(timestamps)) if timestamps else None,
            "latest_ts": str(max(timestamps)) if timestamps else None,
        }

    def record_rule_sql(self, rule_id: str, sql: str) -> None:
        (self.run_dir / "rules" / f"{rule_id}.sql").write_text(sql, encoding="utf-8")

    def record_alerts(self, rule_id: str, alerts: list[dict[str, Any]]) -> str:
        ordered = sorted(alerts, key=lambda a: _canonical_json(a))
        jsonl = b"\n".join(_canonical_json(a) for a in ordered) + (b"\n" if ordered else b"")
        (self.run_dir / "alerts" / f"{rule_id}.jsonl").write_bytes(jsonl)
        digest = _sha256(jsonl)
        (self.run_dir / "alerts" / f"{rule_id}.hash").write_text(digest, encoding="utf-8")
        self.rule_outputs[rule_id] = digest
        return digest

    def record_case(self, case_id: str, case: dict[str, Any]) -> None:
        (self.run_dir / "cases" / f"{case_id}.json").write_bytes(
            json.dumps(case, indent=2, sort_keys=True, default=str).encode("utf-8")
        )

    def append_decision(self, decision: dict[str, Any], ts: datetime | None = None) -> None:
        """Append an engine-time decision. `ts` defaults to `self.as_of` for
        run-to-run determinism. Pass an explicit `ts` only if the caller has a
        deterministic per-decision time (e.g. a simulated resolution time)."""
        stamp = ts if ts is not None else self.as_of
        event = {
            "ts": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
            **decision,
        }
        with (self.run_dir / "decisions.jsonl").open("ab") as f:
            f.write(_canonical_json(event) + b"\n")

    @staticmethod
    def append_to_run_dir(
        run_dir: Path, decision: dict[str, Any], ts: datetime | None = None
    ) -> None:
        """Append a human-time decision to a finalised run.

        Used by the dashboard for analyst actions (escalate, file, close).
        Uses wall-clock `ts` by default — these writes are not part of the
        engine reproducibility contract. Single canonical writer so the
        decisions.jsonl shape stays consistent across the codebase.
        """
        stamp = ts if ts is not None else datetime.now(tz=timezone.utc)
        event = {
            "ts": stamp.isoformat(),
            **decision,
        }
        with (run_dir / "decisions.jsonl").open("ab") as f:
            f.write(_canonical_json(event) + b"\n")

    def finalize(self) -> dict[str, Any]:
        # Compute decision log hash chain for tamper detection.
        decisions_hash = self._compute_decisions_hash()

        manifest = {
            "engine_version": ENGINE_VERSION,
            "run_dir": str(self.run_dir),
            "spec_path": str(self.spec_path),
            "spec_content_hash": self.spec_content_hash,
            "as_of": self.as_of.isoformat(),
            "inputs": self.input_manifest,
            "rule_outputs": self.rule_outputs,
            "decisions_hash": decisions_hash,
            "finalised_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        (self.run_dir / "manifest.json").write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        )
        (self.run_dir / "input_manifest.json").write_bytes(
            json.dumps(self.input_manifest, indent=2, sort_keys=True).encode("utf-8")
        )
        return manifest

    def _compute_decisions_hash(self) -> str:
        """Hash chain over all decisions for tamper detection.

        Each line is hashed with the previous hash to form a chain.
        If any line is modified, the final hash changes.
        """
        decisions_path = self.run_dir / "decisions.jsonl"
        if not decisions_path.exists():
            return _sha256(b"")
        chain_hash = b""
        for line in decisions_path.read_bytes().splitlines():
            if line.strip():
                chain_hash = hashlib.sha256(chain_hash + line).digest()
        return chain_hash.hex()

    @staticmethod
    def verify_decisions(run_dir: Path, expected_hash: str | None = None) -> tuple[bool, str]:
        """Verify the decision log hasn't been tampered with.

        Returns (is_valid, message). When `expected_hash` is provided, the
        chain is compared against that value (the recommended path: pass a
        hash retrieved from an out-of-band store). Otherwise the hash is
        loaded from `manifest.json` in the same `run_dir` — which only
        catches partial tampering, since an attacker who can rewrite the
        decision log can usually rewrite the manifest too.
        """
        if expected_hash is None:
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                return False, "manifest.json not found"

            manifest = json.loads(manifest_path.read_bytes())
            stored_hash = manifest.get("decisions_hash", "")
            if not stored_hash:
                return False, "No decisions_hash in manifest"
        else:
            stored_hash = expected_hash

        decisions_path = run_dir / "decisions.jsonl"
        if not decisions_path.exists():
            computed = _sha256(b"")
        else:
            chain_hash = b""
            for line in decisions_path.read_bytes().splitlines():
                if line.strip():
                    chain_hash = hashlib.sha256(chain_hash + line).digest()
            computed = chain_hash.hex()

        if computed == stored_hash:
            return True, "Decision log integrity verified"
        return False, f"Tamper detected: stored={stored_hash[:16]}... computed={computed[:16]}..."
