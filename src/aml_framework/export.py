"""Package a run directory into a regulator-ready evidence bundle."""

from __future__ import annotations

import zipfile
from pathlib import Path


def export_bundle(run_dir: Path, out_path: Path, spec_path: Path | None = None) -> Path:
    """Zip a run directory. The manifest stays as the first entry so the
    zip index can be inspected without fully extracting.

    If spec_path is provided, includes the control matrix in the bundle.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = run_dir / "manifest.json"
        if manifest.exists():
            zf.write(manifest, arcname="manifest.json")
        for file in sorted(run_dir.rglob("*")):
            if file.is_file() and file != manifest:
                zf.write(file, arcname=str(file.relative_to(run_dir)))

        # Include control matrix if spec is available.
        if spec_path and spec_path.exists():
            try:
                from aml_framework.generators.docs import render_control_matrix
                from aml_framework.spec.loader import load_spec

                spec = load_spec(spec_path)
                matrix_md = render_control_matrix(spec)
                zf.writestr("control_matrix.md", matrix_md)
            except Exception:
                pass  # Don't fail export if control matrix generation fails.

    return out_path
