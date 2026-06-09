"""Pillar-2 defect-ticket lifecycle — issue #529 (Sub-feature A).

The frozen ``defect_log.jsonl`` (see ``engine/defect_log.py``) is the
*minted* defect artifact: one ticket per qualifying issue, pinned by
``defect_log_hash`` on the manifest and frozen post-finalize. That file
answers "what defects did this run surface?" but, by design, is
immutable — it must not change after the run is signed.

A defect, however, has a *lifecycle*: a 2LoD reviewer acknowledges it,
works it, resolves it, and closes it. Recording those transitions on the
frozen log would break its hash. So this module ships a mutable,
append-only **companion** file — ``defect_lifecycle.jsonl`` — that
mirrors the append-only posture of ``decisions.jsonl``: each line is a
single lifecycle transition, appended in order, never rewritten.

Design mirrors ``decisions.jsonl``:
  * append-only (open ``"ab"``, write one canonical-JSON line);
  * deterministic timestamp — the event ``timestamp`` derives from the
    run's ``as_of`` (read from ``manifest.json``), NOT wall-clock, so the
    companion file stays byte-stable for a given (spec, data, as_of)
    plus a given sequence of lifecycle actions;
  * canonical JSON (``sort_keys``) so the line bytes are stable.

This is an OFFLINE, post-run operator action (``aml defect-update``) —
never on the engine run path. The frozen ``defect_log.jsonl`` is the
source of valid defect IDs; a lifecycle event whose ``defect_id`` is not
in the frozen log is rejected so the companion can't drift away from the
artifact it tracks.
"""

from __future__ import annotations

import enum
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The append-only companion file name. Lives next to ``defect_log.jsonl``
# in the run directory.
DEFECT_LIFECYCLE_FILENAME = "defect_lifecycle.jsonl"


class LifecycleStatus(str, enum.Enum):
    """The transitions a defect ticket can be moved into post-mint.

    Mirrors the terminal-ward states of ``DefectStatus`` in
    ``defect_log.py`` (OPEN is the minted state; these are the operator
    transitions). Kept as a separate, smaller enum because a lifecycle
    *event* only ever records a move INTO one of these — it never
    re-asserts OPEN (that's the minted state on the frozen log).
    """

    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DefectLifecycleEvent(BaseModel):
    """One append-only lifecycle transition for a defect ticket.

    Frozen + ``extra="forbid"`` so the JSONL shape is locked, matching
    the ``Defect`` / ``DQException`` posture. The fields follow the issue
    contract: ``{defect_id, lifecycle_status, reviewer, timestamp,
    resolution}``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    defect_id: str = Field(min_length=1)
    lifecycle_status: LifecycleStatus
    reviewer: str = Field(min_length=1)
    timestamp: datetime
    # Free-text resolution note. Required (non-empty) on RESOLVED/CLOSED —
    # a defect can't be resolved/closed without saying how. Optional ("")
    # on ACKNOWLEDGED (the reviewer has merely taken ownership, not fixed
    # anything yet).
    resolution: str = ""

    @model_validator(mode="after")
    def _resolution_required_on_terminal(self) -> "DefectLifecycleEvent":
        if self.lifecycle_status in (LifecycleStatus.RESOLVED, LifecycleStatus.CLOSED):
            if not self.resolution.strip():
                raise ValueError(
                    f"lifecycle_status '{self.lifecycle_status.value}' requires a "
                    "non-empty `resolution` (describe how the defect was addressed)"
                )
        return self


def _canonical_line(event: DefectLifecycleEvent) -> bytes:
    """Serialize a lifecycle event to a single canonical-JSON line.

    ``sort_keys=True`` + ``default=str`` so the bytes are stable across
    re-runs (datetime -> ISO string), matching ``write_defect_log``'s
    byte-stable discipline.
    """
    return json.dumps(event.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")


def read_defect_ids(run_dir: Path) -> set[str]:
    """Return the set of valid defect IDs from the frozen ``defect_log.jsonl``.

    Used to reject a lifecycle event whose ``defect_id`` is not a real
    defect — keeps the companion file from drifting away from the
    artifact it tracks. An empty / missing log yields an empty set.
    """
    path = run_dir / "defect_log.jsonl"
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ids.add(json.loads(line)["id"])
    return ids


def read_lifecycle_events(run_dir: Path) -> list[DefectLifecycleEvent]:
    """Read all lifecycle events from the companion file, in append order.

    Missing file -> empty list (no lifecycle actions taken yet).
    """
    path = run_dir / DEFECT_LIFECYCLE_FILENAME
    if not path.exists():
        return []
    events: list[DefectLifecycleEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(DefectLifecycleEvent.model_validate_json(line))
    return events


def append_lifecycle_event(run_dir: Path, event: DefectLifecycleEvent) -> Path:
    """Append one lifecycle event to ``defect_lifecycle.jsonl``.

    Append-only — opens the file in ``"ab"`` mode and writes a single
    canonical-JSON line. Never rewrites prior lines (mirrors
    ``AuditLedger.append_decision``'s posture on ``decisions.jsonl``).
    Returns the companion file path.
    """
    path = run_dir / DEFECT_LIFECYCLE_FILENAME
    with path.open("ab") as f:
        f.write(_canonical_line(event) + b"\n")
    return path
