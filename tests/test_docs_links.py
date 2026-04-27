"""Documentation link validation.

Catches link rot in README + the new docs/ files when someone moves
or renames a target. Runs in <1s on the unit-test CI image (no
extra deps).

Scope:
  - All `[text](path)` links in README.md and docs/*.md
  - Resolves relative paths against the file's directory
  - Excludes external URLs (http://, https://, mailto:)
  - Excludes pure anchors (#section) without a path
  - Anchor fragments after the path are stripped before existence check
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "ftp://")


def _markdown_files() -> list[Path]:
    """README.md + every docs/*.md file (non-recursive into subdirs)."""
    files = [PROJECT_ROOT / "README.md"]
    files.extend(sorted((PROJECT_ROOT / "docs").glob("*.md")))
    files.append(PROJECT_ROOT / "CHANGELOG.md")
    files.append(PROJECT_ROOT / "CONTRIBUTING.md")
    return [f for f in files if f.exists()]


def _extract_links(md_file: Path) -> list[tuple[str, int]]:
    """Return (target, line_number) pairs for every markdown link."""
    out: list[tuple[str, int]] = []
    for line_num, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
        for match in LINK_RE.finditer(line):
            out.append((match.group(1), line_num))
    return out


def _is_local_link(target: str) -> bool:
    if target.startswith(EXTERNAL_PREFIXES):
        return False
    # Pure anchor like #section — points within the same file, skip.
    if target.startswith("#"):
        return False
    return True


def _resolve(md_file: Path, target: str) -> Path:
    """Resolve a link target relative to the markdown file's directory.

    Strips any #anchor or ?query suffix before path existence check.
    """
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        # Was a pure anchor — already filtered upstream.
        return md_file
    candidate = (md_file.parent / path_part).resolve()
    return candidate


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("md_file", _markdown_files(), ids=lambda p: p.name)
def test_all_local_links_resolve(md_file: Path):
    """Every relative link in README + docs must point at a real file."""
    broken: list[str] = []
    for target, line_num in _extract_links(md_file):
        if not _is_local_link(target):
            continue
        resolved = _resolve(md_file, target)
        if not resolved.exists():
            broken.append(f"  L{line_num}: {target!r} → {resolved}")
    assert not broken, f"{md_file.relative_to(PROJECT_ROOT)} has broken local links:\n" + "\n".join(
        broken
    )


def test_readme_under_target_size():
    """README went from 582 → ~120 lines after the docs hub refactor.
    Guard against drift back toward a monolithic README."""
    readme = PROJECT_ROOT / "README.md"
    line_count = len(readme.read_text(encoding="utf-8").splitlines())
    assert line_count <= 200, (
        f"README.md grew to {line_count} lines (limit 200). "
        "Extract content into a docs/ file and link to it from the docs map."
    )


def test_getting_started_exists():
    """Guard against the Getting Started guide being moved or deleted —
    multiple other docs link to it."""
    assert (PROJECT_ROOT / "docs" / "getting-started.md").exists()


def test_dashboard_tour_exists():
    assert (PROJECT_ROOT / "docs" / "dashboard-tour.md").exists()


def test_jurisdictions_doc_exists():
    assert (PROJECT_ROOT / "docs" / "jurisdictions.md").exists()


def test_readme_has_documentation_map():
    """The README's value as a hub depends on the documentation map being
    intact. If someone removes it, the new-user path breaks."""
    body = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Documentation Map" in body
    # Spot-check that the map links to each new doc.
    assert "docs/getting-started.md" in body
    assert "docs/dashboard-tour.md" in body
    assert "docs/jurisdictions.md" in body
