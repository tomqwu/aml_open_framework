"""Filing-timestamp capture for STR/SAR submissions (PR-DATA-9).

Backs the "Data is the AML problem" whitepaper's DATA-9 claim that
"STR filing-latency p95 is a first-class metric." Before this PR, the
metric was a proxy: `metrics/engine.py:_proxy_filing_latency` computed
p95 from `decisions.jsonl` events with `disposition == "str_filing"`,
treating queue-resolution time as filing time. That over-counts (a case
can be queue-resolved long after the actual STR went out, or vice-versa)
and gives the MLRO a number that doesn't match the regulator's record.

This module adds a sidecar artifact, written when a filing actually
happens:

    <run_dir>/cases/<case_id>__filing.json

with the wall-clock timestamp of submission, the channel (goAML upload,
FinCEN BSA E-Filing, manual-PDF, etc.), and an optional reference id
returned by the receiving system. The metrics engine reads these
sidecars first; the proxy stays as a fallback so legacy runs (no
sidecars) still produce a number.

Why a sidecar (not the bundle):
- `cases/str_bundle.py` is intentionally deterministic — same spec +
  same data + same seed = byte-identical ZIP. Wall-clock filing
  timestamps would break that contract. The sidecar lives alongside
  the case file, written only when a filing event actually occurs,
  separate from the deterministic-rerun artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Channel taxonomy. Open list — institutions add their own; the metrics
# engine doesn't care about specific values, only that a sidecar exists.
COMMON_CHANNELS = (
    "goaml",  # FATF / FINTRAC / EU AMLA — XML upload
    "bsa_e_filing",  # FinCEN — BSA E-Filing System
    "manual_pdf",  # Paper / PDF submission (UK NCA SAR Online too)
    "amla_rts",  # EU AMLA RTS effectiveness pack channel
    "other",
)


@dataclass(frozen=True)
class FilingRecord:
    """One submission to a regulator's filing system."""

    case_id: str
    filed_at: datetime
    channel: str  # one of COMMON_CHANNELS or institution-specific
    reference_id: str = ""  # confirmation number returned by the receiver
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "filed_at": self.filed_at.isoformat(),
            "channel": self.channel,
            "reference_id": self.reference_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FilingRecord":
        filed_at = d["filed_at"]
        if isinstance(filed_at, str):
            filed_at = datetime.fromisoformat(filed_at.replace("Z", "+00:00"))
        return cls(
            case_id=d["case_id"],
            filed_at=filed_at,
            channel=d.get("channel", "other"),
            reference_id=d.get("reference_id", ""),
            notes=d.get("notes", ""),
        )


def filing_path(run_dir: Path, case_id: str) -> Path:
    """Sidecar path for a case's filing record. Lives next to the case
    JSON so a regulator pulling the run dir gets case + filing together.
    """
    return run_dir / "cases" / f"{case_id}__filing.json"


def record_filing(
    run_dir: Path,
    case_id: str,
    *,
    filed_at: datetime,
    channel: str = "other",
    reference_id: str = "",
    notes: str = "",
) -> FilingRecord:
    """Write a filing sidecar for `case_id` in `run_dir`.

    Idempotent: writing twice with the same `filed_at` overwrites the
    file with identical bytes (used by re-tries that re-submit on
    transport failure). If `filed_at` differs, the new record wins —
    the latest filing time is the authoritative one for latency
    calculations. The previous record is overwritten silently; if you
    need an audit trail of every submission attempt, append to the
    `notes` field.
    """
    if filed_at.tzinfo is None:
        # Normalise naive timestamps to UTC so latency math doesn't
        # get tripped up by a half-set timezone.
        filed_at = filed_at.replace(tzinfo=timezone.utc)
    record = FilingRecord(
        case_id=case_id,
        filed_at=filed_at,
        channel=channel,
        reference_id=reference_id,
        notes=notes,
    )
    path = filing_path(run_dir, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def get_filing(run_dir: Path, case_id: str) -> FilingRecord | None:
    """Read the filing sidecar for `case_id`, or None if no filing has
    been recorded yet (most cases — only filed STR/SAR cases have one).
    """
    path = filing_path(run_dir, case_id)
    if not path.exists():
        return None
    try:
        return FilingRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def list_filings(run_dir: Path) -> list[FilingRecord]:
    """Every filing sidecar under a run dir, sorted by case_id."""
    cases_dir = run_dir / "cases"
    if not cases_dir.exists():
        return []
    out: list[FilingRecord] = []
    for path in sorted(cases_dir.glob("*__filing.json")):
        try:
            out.append(FilingRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out


def filing_latency_days(record: FilingRecord, case_opened_at: datetime) -> float:
    """Wall-clock days between a case being opened and its filing.

    Both arguments are tz-aware (caller is responsible). Returns 0.0
    for filings that pre-date case open (clock skew or backdated entry)
    rather than going negative — negative latency would skew the p95
    metric pathologically.
    """
    if case_opened_at.tzinfo is None:
        case_opened_at = case_opened_at.replace(tzinfo=timezone.utc)
    if record.filed_at.tzinfo is None:
        rec_at = record.filed_at.replace(tzinfo=timezone.utc)
    else:
        rec_at = record.filed_at
    delta = rec_at - case_opened_at
    return max(0.0, delta.total_seconds() / 86400.0)
