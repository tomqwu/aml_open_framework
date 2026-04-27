"""SHA-256 content cache + delta-diff for sanctions list updates.

Why a cache: the framework's `list_match` rules read flat CSVs from
`data/lists/<name>.csv`. Re-pulling the same upstream payload should be
a no-op (no file rewrites, no rule re-runs). We hash the canonical CSV
representation, store the hash + metadata in a sidecar `.cache/<name>.meta.json`,
and only rewrite the CSV when the new payload differs.

Diff output: every `sync()` returns a `SyncResult` listing which entries
were added vs removed since the last cached state, so operators can
preview before merging into production lists.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from aml_framework.sanctions.base import SanctionEntry

_CSV_HEADER = ["name", "list_source", "country", "type"]


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a single feed sync."""

    list_name: str
    sha256: str
    row_count: int
    added: list[SanctionEntry] = field(default_factory=list)
    removed: list[SanctionEntry] = field(default_factory=list)
    unchanged: bool = False
    csv_path: Path | None = None

    @property
    def changed(self) -> int:
        return len(self.added) + len(self.removed)


def _canonical_csv(entries: list[SanctionEntry]) -> bytes:
    """CSV bytes with sorted rows so identical inputs hash identically."""
    rows = sorted(
        (e.csv_row() for e in entries),
        key=lambda r: (r["list_source"], r["name"], r["country"], r["type"]),
    )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_HEADER, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _read_csv_entries(path: Path) -> list[SanctionEntry]:
    if not path.exists():
        return []
    out: list[SanctionEntry] = []
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(
                SanctionEntry(
                    name=row.get("name", ""),
                    list_source=row.get("list_source", ""),
                    country=row.get("country", ""),
                    type=row.get("type", "individual"),
                )
            )
    return out


@dataclass(frozen=True)
class SanctionsCache:
    """Manages `data/lists/<name>.csv` + sidecar metadata.

    `lists_dir` defaults to the bundled `aml_framework/data/lists/`; tests
    pass a tmp_path so they don't touch packaged data.
    """

    lists_dir: Path

    @property
    def meta_dir(self) -> Path:
        return self.lists_dir / ".cache"

    def _csv_path(self, list_name: str) -> Path:
        return self.lists_dir / f"{list_name}.csv"

    def _meta_path(self, list_name: str) -> Path:
        return self.meta_dir / f"{list_name}.meta.json"

    def read_meta(self, list_name: str) -> dict | None:
        path = self._meta_path(list_name)
        if not path.exists():
            return None
        return json.loads(path.read_bytes())

    def write(
        self,
        list_name: str,
        entries: list[SanctionEntry],
        *,
        source_url: str | None = None,
    ) -> SyncResult:
        """Write entries to `<list_name>.csv` if the canonical hash changed.

        Returns a SyncResult with added/removed deltas vs the previous
        on-disk content. When unchanged, no files are written.
        """
        self.lists_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

        new_payload = _canonical_csv(entries)
        new_sha = hashlib.sha256(new_payload).hexdigest()

        previous_meta = self.read_meta(list_name)
        previous_sha = (previous_meta or {}).get("sha256")

        csv_path = self._csv_path(list_name)
        old_entries = _read_csv_entries(csv_path)

        if previous_sha == new_sha and csv_path.exists():
            return SyncResult(
                list_name=list_name,
                sha256=new_sha,
                row_count=len(entries),
                unchanged=True,
                csv_path=csv_path,
            )

        old_keys = {(e.list_source, e.name, e.country, e.type) for e in old_entries}
        new_keys = {(e.list_source, e.name, e.country, e.type) for e in entries}
        added_keys = new_keys - old_keys
        removed_keys = old_keys - new_keys

        added = sorted(
            (e for e in entries if (e.list_source, e.name, e.country, e.type) in added_keys),
            key=lambda e: (e.list_source, e.name),
        )
        removed = sorted(
            (e for e in old_entries if (e.list_source, e.name, e.country, e.type) in removed_keys),
            key=lambda e: (e.list_source, e.name),
        )

        csv_path.write_bytes(new_payload)
        meta = {
            "sha256": new_sha,
            "row_count": len(entries),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
            "source_url": source_url,
            "added_count": len(added),
            "removed_count": len(removed),
        }
        self._meta_path(list_name).write_bytes(
            json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
        )

        return SyncResult(
            list_name=list_name,
            sha256=new_sha,
            row_count=len(entries),
            added=added,
            removed=removed,
            unchanged=False,
            csv_path=csv_path,
        )
