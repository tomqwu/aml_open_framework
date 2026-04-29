"""Auditor self-service bundle — one ZIP, one command, no IT call.

Process problem this solves
---------------------------
When the regulator (or internal audit) walks in, today the auditor
asks for evidence and IT spends 1-3 days assembling: extracting the
ledger, regenerating reports, finding the right manifest, building
the examination ZIP. Many of those days are "find the right SharePoint
folder," not actual analysis.

`aml auditor-pack` collapses that into one command. It:

  1. Verifies the SHA-256 hash chain on the run's `decisions.jsonl`
     and writes the result + timestamp into the bundle (so the
     auditor doesn't have to take our word for it)
  2. Builds the regulator audit pack (jurisdiction-aware: FINTRAC /
     FCA / OSFI / FinCEN section maps)
  3. Builds the FinCEN effectiveness pack when the spec carries
     `aml_priority` fields
  4. Copies the spec snapshot, the manifest, and the raw audit log
     (decisions.jsonl) into the bundle
  5. Writes a one-page MANIFEST.txt index — the first file the
     auditor sees, telling them what each piece is and which
     regulation clause it answers

Output is a single ZIP the auditor downloads from a shared drive or
that gets emailed to them. No further IT involvement; no further
re-extraction; chain-verified at the moment the bundle was built.

Design choices
--------------
- One ZIP, not a directory of files. Auditors prefer attachable
  artifacts; trying to share a directory tree across email is exactly
  the manual process this replaces.
- MANIFEST.txt is plaintext, written first inside the ZIP. An auditor
  who only opens Notepad sees the full structure.
- Effectiveness pack is included when the spec supports it; gracefully
  skipped otherwise — the wizard never half-fails.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Files we always try to copy into the bundle (when present in the run dir).
# Everything else is generated.
_RUN_DIR_FILES_TO_INCLUDE = (
    "manifest.json",
    "decisions.jsonl",
    "spec_snapshot.yaml",
)


@dataclass(frozen=True)
class AuditorPackResult:
    """What `build_auditor_pack` produced — for the CLI to narrate."""

    zip_path: Path
    chain_verified: bool
    chain_message: str
    components: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zip_path": str(self.zip_path),
            "chain_verified": self.chain_verified,
            "chain_message": self.chain_message,
            "components": list(self.components),
            "n_components": len(self.components),
        }


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_manifest_txt(
    *,
    program_name: str,
    jurisdiction: str,
    regulator: str,
    run_dir: Path,
    chain_verified: bool,
    chain_message: str,
    components: list[str],
    built_at: str,
    bundle_sha256: str,
) -> str:
    """One-page index. Auditor opens this file first."""
    chain_line = (
        f"  ✓ verified at {built_at}"
        if chain_verified
        else f"  ✗ TAMPER SUSPECTED — {chain_message}"
    )
    component_lines = "\n".join(f"  - {c}" for c in components)
    return f"""AML Open Framework — Auditor Pack
==================================

Program       : {program_name}
Jurisdiction  : {jurisdiction}
Regulator     : {regulator}
Run dir       : {run_dir.name}
Built at      : {built_at}
Bundle SHA-256: {bundle_sha256}

Chain integrity
---------------
{chain_line}
  {chain_message}

Contents
--------
{component_lines}

What each file is
-----------------
- MANIFEST.txt          This index (you are here).
- audit_pack.zip        Regulator examination ZIP — section-mapped to
                        the relevant clauses (PCMLTFA / OSFI / FCA /
                        FinCEN). Hand this to the examiner.
- effectiveness.json    FinCEN April 2026 NPRM effectiveness-pack
                        (4 pillars: risk-assessment alignment, AML/CFT
                        priority coverage, control-output quality,
                        feedback-loop evidence). Present when the spec
                        carries `aml_priority` fields.
- decisions.jsonl       Append-only, hash-chained audit ledger. Run
                        `aml replay` to reproduce any historical run
                        byte-for-byte and confirm the hashes match.
- manifest.json         Run manifest — spec hash, output hashes,
                        engine version, timestamp.
- spec_snapshot.yaml    The spec exactly as it ran. Replay against
                        this for byte-for-byte verification.

Verification
------------
To independently verify the chain:

    aml replay {program_name} --run-dir <extracted-decisions.jsonl-dir>

If the replay's output hashes match the manifest's, the run is
reproducible and the evidence chain is intact.
"""


def _verify_chain(run_dir: Path) -> tuple[bool, str]:
    """Run the framework's built-in chain verifier; tolerate missing modules."""
    try:
        from aml_framework.engine.audit import AuditLedger

        return AuditLedger.verify_decisions(run_dir)
    except Exception as e:
        # Chain verification should never crash the bundle build —
        # we surface the error in the manifest instead.
        return False, f"Verifier raised {type(e).__name__}: {e}"


def build_auditor_pack(
    spec: Any,
    run_dir: Path,
    *,
    out: Path,
    jurisdiction: str | None = None,
) -> AuditorPackResult:
    """Build a one-stop auditor bundle ZIP. Returns a result for CLI to narrate.

    Args:
        spec: Loaded `AMLSpec` from `aml_framework.spec.load_spec(...)`.
        run_dir: Directory of an existing engine run — must contain at
            least `manifest.json` and `decisions.jsonl`.
        out: Where to write the ZIP. Parent dir is created if needed.
        jurisdiction: Override jurisdiction for the audit-pack template
            (defaults to a derived `<JURISDICTION>-<REGULATOR>` slug).
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")

    out.parent.mkdir(parents=True, exist_ok=True)
    components: list[str] = ["MANIFEST.txt"]
    chain_ok, chain_msg = _verify_chain(run_dir)

    # Build inner artifacts in-memory so we can include them in the ZIP
    # before computing the bundle's own SHA-256.
    pieces: dict[str, bytes] = {}

    # 1. Audit pack (jurisdiction-aware regulator examination ZIP).
    juris = jurisdiction or f"{spec.program.jurisdiction}-{spec.program.regulator}"
    try:
        from aml_framework.generators.audit_pack import build_audit_pack_from_run_dir

        pieces["audit_pack.zip"] = build_audit_pack_from_run_dir(spec, run_dir, jurisdiction=juris)
        components.append("audit_pack.zip")
    except Exception:
        # Audit pack is best-effort — if a jurisdiction template is
        # missing, we still ship the rest of the bundle rather than
        # failing the whole command.
        pass

    # 2. Effectiveness pack (when spec supports it).
    has_priority = any(getattr(r, "aml_priority", None) for r in spec.rules)
    if has_priority:
        try:
            from aml_framework.generators.effectiveness import (
                export_pack_from_run_dir as _export_eff_pack,
            )

            pieces["effectiveness.json"] = _export_eff_pack(spec, run_dir)
            components.append("effectiveness.json")
        except Exception:
            pass

    # 3. Copy raw run-dir files we want the auditor to have.
    for name in _RUN_DIR_FILES_TO_INCLUDE:
        f = run_dir / name
        if f.exists():
            pieces[name] = f.read_bytes()
            components.append(name)

    # 4. Compute the bundle's own SHA-256 over the deterministic
    # (sorted) concatenation of inner files. Auditor uses this to
    # confirm the bundle wasn't tampered with after build.
    h = hashlib.sha256()
    for name in sorted(pieces):
        h.update(name.encode("utf-8"))
        h.update(pieces[name])
    bundle_sha256 = h.hexdigest()

    # 5. Manifest goes in last because it references the bundle hash.
    manifest_txt = _render_manifest_txt(
        program_name=spec.program.name,
        jurisdiction=spec.program.jurisdiction,
        regulator=spec.program.regulator,
        run_dir=run_dir,
        chain_verified=chain_ok,
        chain_message=chain_msg,
        components=components,
        built_at=_utc_now_iso(),
        bundle_sha256=bundle_sha256,
    )

    # 6. Write the ZIP.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # MANIFEST.txt first so unzipping streams it first.
        z.writestr("MANIFEST.txt", manifest_txt)
        for name in sorted(pieces):
            z.writestr(name, pieces[name])
    out.write_bytes(buf.getvalue())

    return AuditorPackResult(
        zip_path=out,
        chain_verified=chain_ok,
        chain_message=chain_msg,
        components=components,
    )


def auditor_dashboard_url(
    spec_path: Path,
    *,
    host: str = "http://localhost:8501",
) -> str:
    """Return a deep-link URL the auditor can paste into a browser to
    open the dashboard pre-filtered to the Auditor persona on the
    Audit & Evidence page.

    Streamlit query parameters survive a manual refresh, so this is
    safe to share via email or a corporate portal.
    """
    return f"{host}/?audience=auditor&page=Audit+%26+Evidence&spec={spec_path.name}"
