"""Package a run directory into a regulator-ready evidence bundle."""

from __future__ import annotations

import zipfile
from pathlib import Path


def export_bundle(run_dir: Path, out_path: Path) -> Path:
    """Zip a run directory. The manifest stays as the first entry so the
    zip index can be inspected without fully extracting."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = run_dir / "manifest.json"
        if manifest.exists():
            zf.write(manifest, arcname="manifest.json")
        for file in sorted(run_dir.rglob("*")):
            if file.is_file() and file != manifest:
                zf.write(file, arcname=str(file.relative_to(run_dir)))
    return out_path
