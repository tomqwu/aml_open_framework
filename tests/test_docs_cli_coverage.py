"""CLI doc-coverage gate (PR-DOCS-4 / R32 follow-up).

Asserts that every `aml <command>` registered on the Typer CLI is
mentioned in at least one user-facing doc surface. The intent is the
mechanical version of the standing rule in CLAUDE.md and memory
``feedback_every_change_needs_tests_and_docs.md``: every new CLI command
ships with a doc mention, so operators can discover it without grepping
the source.

The pattern mirrors `tests/test_docs_links.py::test_readme_under_target_size`
and `tests/test_dashboard_tour_coverage.py::TestTourMentionsEveryPage` —
defensive gates checked into CI so the discipline doesn't depend on
reviewer attention.

**No-new-debt model**: a sizeable backlog of commands already lacked
doc mentions when this test was added (R32). Rather than block all
work on closing that backlog in one shot, the test allows the existing
gap via `KNOWN_UNDOCUMENTED` and refuses to let it grow. To remove
an entry from the allowlist you must add a doc mention.
"""

from __future__ import annotations

import re
from pathlib import Path

from aml_framework.cli import app

ROOT = Path(__file__).resolve().parent.parent

# Doc surfaces where an `aml <cmd>` mention counts as documentation.
# Keep the list short and high-signal — README is the primary discovery
# surface; getting-started is the onboarding flow; how-to/ recipes are
# task-oriented; legacy-import is a sibling how-to.
DOC_SURFACES: tuple[Path, ...] = (
    ROOT / "README.md",
    ROOT / "docs" / "getting-started.md",
    ROOT / "docs" / "legacy-import.md",
)
HOW_TO_DIR = ROOT / "docs" / "how-to"


# Commands without a current doc mention. Each one is a TODO for a
# follow-up PR. Removing an entry requires adding the doc mention.
# Adding an entry requires reviewer pushback — the test exists to
# prevent that.
KNOWN_UNDOCUMENTED: frozenset[str] = frozenset(
    {
        "add-rule",
        "attest",
        "backtest",
        "byod",
        "diff",
        "draft-narrative",
        "effectiveness-pack",
        "email-digest",
        "export-alerts",
        "export-amla-str",
        "export-goaml",
        "generate",
        "generate-dbt",
        "init",
        "mrm-bundle",
        # notify-digest documented in docs/how-to/configure-sla.md (PR-DOCS-3).
        "outcomes-pack",
        "pkyc-scan",
        "propose-change",
        "queue-rank",
        "regwatch",
        "replay",
        "report",
        "sanctions-sync",
        "schedule",
        "share-pattern",
        "today",
        "typology-import",
        "typology-list",
        "validate-data",
        "verify-pattern",
    }
)


def _registered_command_names() -> set[str]:
    """Extract `aml <subcommand>` names from the Typer app."""
    names: set[str] = set()
    for cmd in app.registered_commands:
        if cmd.name:
            names.add(cmd.name)
        elif cmd.callback is not None and getattr(cmd.callback, "__name__", ""):
            # Fallback for unnamed commands — derive from callable name.
            # Typer convention: `foo_bar_cmd` → `foo-bar`.
            raw = cmd.callback.__name__.removesuffix("_cmd").replace("_", "-")
            names.add(raw)
    return names


def _doc_body() -> str:
    """Concatenated text from every doc surface — fast to grep against."""
    paths = list(DOC_SURFACES) + sorted(HOW_TO_DIR.glob("*.md"))
    chunks: list[str] = []
    for p in paths:
        if p.exists():
            chunks.append(p.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _undocumented(commands: set[str], body: str) -> set[str]:
    """Return the commands that don't appear as `aml <cmd>` anywhere."""
    missing: set[str] = set()
    for cmd in commands:
        # Match `aml foo` or `aml \nfoo` (in code blocks) — but require
        # a word boundary after the command name so `aml validate` doesn't
        # accidentally match `aml validate-data`.
        if not re.search(rf"`?aml {re.escape(cmd)}\b", body):
            missing.add(cmd)
    return missing


class TestCliDocCoverage:
    """Gate: every aml command must be mentioned somewhere in the
    discovery-path docs."""

    def test_every_command_appears_in_a_doc_or_is_allowlisted(self):
        commands = _registered_command_names()
        body = _doc_body()
        missing = _undocumented(commands, body)
        # Commands missing AND not on the allowlist are the failure mode.
        new_debt = missing - KNOWN_UNDOCUMENTED
        assert not new_debt, (
            "These CLI commands have no documentation mention "
            "(`aml <cmd>`) in README.md / docs/getting-started.md / "
            "docs/legacy-import.md / docs/how-to/*.md:\n  "
            + "\n  ".join(sorted(new_debt))
            + "\n\nEither add a doc mention or, if intentionally undocumented, "
            "add to KNOWN_UNDOCUMENTED in tests/test_docs_cli_coverage.py "
            "(reviewer pushback expected)."
        )

    def test_allowlist_does_not_grow_silently(self):
        """The allowlist is debt — entries that no longer apply (the
        command was documented OR removed) must be cleaned up. This
        check catches stale allowlist entries so the gate stays honest."""
        commands = _registered_command_names()
        body = _doc_body()
        actually_undocumented = _undocumented(commands, body)
        # An allowlist entry is stale if the command is now documented
        # OR if the command was removed from the CLI.
        stale = set()
        for cmd in KNOWN_UNDOCUMENTED:
            if cmd not in commands:
                stale.add(f"{cmd} (removed from CLI)")
            elif cmd not in actually_undocumented:
                stale.add(f"{cmd} (now documented)")
        assert not stale, (
            "These KNOWN_UNDOCUMENTED entries are stale — remove them:\n  "
            + "\n  ".join(sorted(stale))
        )
