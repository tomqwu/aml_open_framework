"""MLRO attestation workflow (PR-DATA-8).

Backs the "Data is the AML problem" whitepaper's DATA-8 claim that
"the MLRO's signature on a control attestation references a Manifest
version — by hash, unambiguous about what the program covered, when."

Before this PR, the framework had assessment dashboard pages
(Program Maturity, Framework Alignment) but no signing workflow —
nothing concrete the MLRO could "sign." This module adds:

- `Attestation` — a hash-anchored record of an MLRO sign-off on a
  specific spec_content_hash, with officer ID, timestamp, and
  optional notes.
- `AttestationLedger` — append-only, hash-chained `attestations.jsonl`
  in a configurable artifacts dir (default `./.attestations/`).
  Lives parallel to the audit ledger; chained for tamper detection.
- `latest_attestation_for_spec(spec_hash)` — reader used by `aml run
  --strict` to enforce attestation as a precondition for execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ATTESTATIONS_DIR = Path(".attestations")
ATTESTATION_LEDGER_FILENAME = "attestations.jsonl"


@dataclass(frozen=True)
class Attestation:
    """One MLRO sign-off against a specific spec_content_hash.

    The pair (spec_content_hash, officer_id, ts) uniquely identifies
    the attestation. `prev_hash` chains to the previous attestation in
    the ledger for tamper detection — same pattern as `decisions.jsonl`.
    """

    officer_id: str
    spec_content_hash: str
    ts: datetime
    notes: str = ""
    prev_hash: str = ""  # SHA-256 of the previous canonicalised entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "officer_id": self.officer_id,
            "spec_content_hash": self.spec_content_hash,
            "ts": self.ts.isoformat(),
            "notes": self.notes,
            "prev_hash": self.prev_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Attestation":
        ts = d["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(
            officer_id=d["officer_id"],
            spec_content_hash=d["spec_content_hash"],
            ts=ts,
            notes=d.get("notes", ""),
            prev_hash=d.get("prev_hash", ""),
        )

    def content_hash(self) -> str:
        """SHA-256 over the canonicalised body — used as the next
        entry's `prev_hash`."""
        body = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(body).hexdigest()


@dataclass
class AttestationLedger:
    """Append-only hash-chained ledger of MLRO attestations.

    Lives at `<dir>/attestations.jsonl`. Tamper detection: each entry
    carries the `prev_hash` of the entry before it; rewriting any line
    breaks the chain. `verify()` walks the chain and reports the first
    break.
    """

    dir: Path = field(default_factory=lambda: DEFAULT_ATTESTATIONS_DIR)

    @property
    def path(self) -> Path:
        return self.dir / ATTESTATION_LEDGER_FILENAME

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[Attestation]:
        """Every attestation in chronological (file) order."""
        if not self.path.exists():
            return []
        out: list[Attestation] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(Attestation.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def append(
        self,
        *,
        officer_id: str,
        spec_content_hash: str,
        notes: str = "",
        ts: datetime | None = None,
    ) -> Attestation:
        """Append a new attestation, chaining to the previous entry."""
        self._ensure_dir()
        existing = self.all()
        prev_hash = existing[-1].content_hash() if existing else ""
        attestation = Attestation(
            officer_id=officer_id,
            spec_content_hash=spec_content_hash,
            ts=ts or datetime.now(tz=timezone.utc),
            notes=notes,
            prev_hash=prev_hash,
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(attestation.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        return attestation

    def latest_for_spec(self, spec_content_hash: str) -> Attestation | None:
        """Most-recent attestation against this exact spec hash, or None.

        Used by `aml run --strict` to enforce attestation as a
        precondition: if the spec the engine is about to execute has
        not been signed against by an MLRO, the run is refused.
        """
        matches = [a for a in self.all() if a.spec_content_hash == spec_content_hash]
        return matches[-1] if matches else None

    def verify(self) -> tuple[bool, str]:
        """Walk the hash chain. Returns (ok, message).

        Each entry's `prev_hash` must equal the previous entry's
        `content_hash()`. The first entry must have `prev_hash=""`.
        """
        entries = self.all()
        if not entries:
            return True, "ledger is empty"
        if entries[0].prev_hash != "":
            return False, "first entry has non-empty prev_hash (chain head broken)"
        for i in range(1, len(entries)):
            expected = entries[i - 1].content_hash()
            if entries[i].prev_hash != expected:
                return False, (
                    f"chain break at entry {i} (officer={entries[i].officer_id}, "
                    f"spec={entries[i].spec_content_hash[:16]}…): "
                    f"expected prev_hash {expected[:16]}…, got {entries[i].prev_hash[:16]}…"
                )
        return True, f"chain verified ({len(entries)} entr{'y' if len(entries) == 1 else 'ies'})"
