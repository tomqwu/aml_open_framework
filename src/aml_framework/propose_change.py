"""`aml propose-change` — package a threshold change as a 2LoD review packet.

Process problem this solves
---------------------------
When 1LoD wants to change a threshold (tighten structuring from
$10k to $9.5k, widen the window from 7 to 30 days), the 2LoD review
ritual today happens in email or a SharePoint Word doc. The change
rationale isn't archived with the spec PR; the auditor asking
"why was this changed?" 6 months later finds an Outlook thread.

This module produces a structured **MLRO Review Packet** — Markdown
the 2LoD reads in their PR, with:

  - Diff: current rule YAML vs proposed YAML, side-by-side
  - Alert delta: how many alerts the change adds / removes / shifts,
    with planted-positive impact (precision/recall when labels exist)
  - Regulation cite: the citation the rule already carries; the
    review packet preserves it so 2LoD doesn't have to re-look it up
  - Sign-off block: empty cells for 2LoD name, date, decision —
    1LoD fills the top, 2LoD fills the bottom in the PR review

The packet is the merge artifact that lives next to the spec change
in the audit trail. When OSFI walks in 18 months later and asks
"who decided to lower this threshold?", the answer is in the spec
PR's commit history.

Pure-function generator. CLI command writes to disk; tests cover the
generator directly so they don't need a webhook or a PR API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProposedChange:
    """Inputs the wizard captures."""

    spec_path: Path
    rule_id: str
    proposed_yaml: str  # full YAML of the rule after the change
    proposer: str  # 1LoD name (defaults to git user.name when None)
    rationale: str  # one paragraph; what + why
    expected_impact: str = ""  # optional; what the proposer expects to see


@dataclass(frozen=True)
class AlertDelta:
    """Snapshot of how the change affects alerts on the current run.

    Computed by re-running just this rule (via `engine.tuning.sweep_rule`)
    against the same data, with the proposed thresholds. Test code can
    construct this directly without invoking the engine.
    """

    baseline_alert_count: int
    proposed_alert_count: int
    added_customers: list[str]  # alerts that newly fire
    removed_customers: list[str]  # alerts that stop firing
    precision_baseline: float | None = None
    precision_proposed: float | None = None
    recall_baseline: float | None = None
    recall_proposed: float | None = None

    @property
    def net(self) -> int:
        return self.proposed_alert_count - self.baseline_alert_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_alert_count": self.baseline_alert_count,
            "proposed_alert_count": self.proposed_alert_count,
            "net": self.net,
            "added_customers": list(self.added_customers),
            "removed_customers": list(self.removed_customers),
            "precision_baseline": self.precision_baseline,
            "precision_proposed": self.precision_proposed,
            "recall_baseline": self.recall_baseline,
            "recall_proposed": self.recall_proposed,
        }


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------


def _extract_rule_yaml(spec_text: str, rule_id: str) -> str | None:
    """Pull the YAML block for a single rule from the full spec text.

    Cheap text-based extraction — finds `- id: <rule_id>` and walks
    forward until either:
      - the next `- id:` line at the same indent (next rule), or
      - a top-level key (column-0) that ends the rules block.
    """
    lines = spec_text.splitlines()
    start = None
    indent: str | None = None

    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)- id:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
        if m and m.group(2) == rule_id:
            start = i
            indent = m.group(1)
            break
    if start is None or indent is None:
        return None

    # Walk forward to find the end.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.startswith(f"{indent}- id:"):
            end = j
            break
        # Top-level key (no leading whitespace, non-comment, non-blank)
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            end = j
            break
    return "\n".join(lines[start:end]).rstrip() + "\n"


def render_unified_diff(current_yaml: str, proposed_yaml: str) -> str:
    """Standard unified diff with a tighter +/- prefix for Markdown rendering."""
    import difflib

    diff = difflib.unified_diff(
        current_yaml.splitlines(keepends=False),
        proposed_yaml.splitlines(keepends=False),
        fromfile="current",
        tofile="proposed",
        lineterm="",
    )
    return "\n".join(diff)


# ---------------------------------------------------------------------------
# Sign-off packet
# ---------------------------------------------------------------------------


def render_review_packet(
    *,
    change: ProposedChange,
    current_yaml: str,
    delta: AlertDelta | None = None,
    citations: list[str] | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Render the full Markdown review packet.

    Sections in order:
      1. Header (rule id, proposer, date)
      2. Rationale (what + why)
      3. Expected impact (proposer's prediction)
      4. Current vs proposed diff (unified)
      5. Alert delta (when supplied)
      6. Regulation citations (preserved from current rule)
      7. 2LoD sign-off block (empty fields)
    """
    ts = (generated_at or datetime.now(tz=timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    diff = render_unified_diff(current_yaml, change.proposed_yaml)
    citations_md = (
        "\n".join(f"- {c}" for c in citations) if citations else "_(no citations parsed)_"
    )

    delta_md = "_(no delta computed — re-run with `--with-impact` to attach)_"
    if delta is not None:
        delta_md = (
            f"| Metric | Baseline | Proposed | Δ |\n"
            f"|---|---|---|---|\n"
            f"| Alerts | {delta.baseline_alert_count} | {delta.proposed_alert_count} "
            f"| {delta.net:+d} |\n"
        )
        if delta.precision_baseline is not None and delta.precision_proposed is not None:
            delta_md += (
                f"| Precision | {delta.precision_baseline:.3f} "
                f"| {delta.precision_proposed:.3f} "
                f"| {delta.precision_proposed - delta.precision_baseline:+.3f} |\n"
            )
        if delta.recall_baseline is not None and delta.recall_proposed is not None:
            delta_md += (
                f"| Recall | {delta.recall_baseline:.3f} "
                f"| {delta.recall_proposed:.3f} "
                f"| {delta.recall_proposed - delta.recall_baseline:+.3f} |\n"
            )
        delta_md += "\n"
        if delta.added_customers:
            delta_md += (
                f"\n**Customers newly alerting** ({len(delta.added_customers)}): "
                + ", ".join(f"`{c}`" for c in delta.added_customers[:10])
            )
            if len(delta.added_customers) > 10:
                delta_md += f" …and {len(delta.added_customers) - 10} more"
        if delta.removed_customers:
            delta_md += (
                f"\n**Customers no longer alerting** ({len(delta.removed_customers)}): "
                + ", ".join(f"`{c}`" for c in delta.removed_customers[:10])
            )
            if len(delta.removed_customers) > 10:
                delta_md += f" …and {len(delta.removed_customers) - 10} more"

    return f"""# MLRO Review Packet · `{change.rule_id}`

**Proposer:** {change.proposer}
**Generated:** {ts}
**Spec:** `{change.spec_path}`

## 1. Rationale

{change.rationale}

## 2. Expected impact

{change.expected_impact or "_(not provided — proposer should add a 1-line prediction)_"}

## 3. Diff (current → proposed)

```diff
{diff}
```

## 4. Alert delta

{delta_md}

## 5. Regulation citations (preserved from current rule)

{citations_md}

## 6. 2LoD sign-off

| Role | Name | Date | Decision | Notes |
|---|---|---|---|---|
| **Proposer (1LoD)** | {change.proposer} | {ts[:10]} | _Submitted_ | _(rationale above)_ |
| **2LoD Reviewer** | _(fill in)_ | _(fill in)_ | _( ) Approve · ( ) Reject · ( ) Defer_ | _(fill in)_ |
| **MLRO Sign-off** | _(fill in)_ | _(fill in)_ | _( ) Approve · ( ) Reject_ | _(fill in)_ |

---

_This packet is the audit-trail artifact for the spec change. Save it
in the PR description; the spec PR + this packet together answer the
auditor's "who decided?" question 18 months later._
"""


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------


def extract_citations(rule_yaml: str) -> list[str]:
    """Pull the regulation citations from a rule's YAML block."""
    citations: list[str] = []
    for line in rule_yaml.splitlines():
        m = re.match(r"\s*-\s*citation:\s*\"([^\"]+)\"", line)
        if not m:
            m = re.match(r"\s*-\s*citation:\s*'([^']+)'", line)
        if m:
            citations.append(m.group(1))
    return citations


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build_review_packet(
    *,
    change: ProposedChange,
    current_yaml: str | None = None,
    delta: AlertDelta | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Convenience wrapper: read the current rule from spec_path if not
    supplied, extract citations, render the packet."""
    if current_yaml is None:
        spec_text = change.spec_path.read_text(encoding="utf-8")
        current_yaml = _extract_rule_yaml(spec_text, change.rule_id) or ""
    citations = extract_citations(current_yaml)
    return render_review_packet(
        change=change,
        current_yaml=current_yaml,
        delta=delta,
        citations=citations,
        generated_at=generated_at,
    )
