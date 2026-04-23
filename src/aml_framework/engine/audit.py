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

Hashes are SHA-256 over canonicalised bytes. Decision events are append-only;
the framework never rewrites this file — an attempted mutation is considered
a control-integrity failure.
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
    def create(cls, artifacts_root: Path, spec_path: Path, spec_hash: str, as_of: datetime) -> "AuditLedger":
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

    def append_decision(self, decision: dict[str, Any]) -> None:
        event = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            **decision,
        }
        with (self.run_dir / "decisions.jsonl").open("ab") as f:
            f.write(_canonical_json(event) + b"\n")

    def finalize(self) -> dict[str, Any]:
        manifest = {
            "engine_version": ENGINE_VERSION,
            "run_dir": str(self.run_dir),
            "spec_path": str(self.spec_path),
            "spec_content_hash": self.spec_content_hash,
            "as_of": self.as_of.isoformat(),
            "inputs": self.input_manifest,
            "rule_outputs": self.rule_outputs,
            "finalised_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        (self.run_dir / "manifest.json").write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        )
        (self.run_dir / "input_manifest.json").write_bytes(
            json.dumps(self.input_manifest, indent=2, sort_keys=True).encode("utf-8")
        )
        return manifest
