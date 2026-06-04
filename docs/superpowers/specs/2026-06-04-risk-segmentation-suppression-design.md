# Risk Segmentation + Governed Alert Suppression — Design (#495)

**Status:** design locked 2026-06-04. Next-tier ML/AI roadmap (Pillar 5). Implements "ML FP-reduction + risk segmentation (governed suppression)."

## Problem
Legacy AML rules over-fire (industry FP rates 90%+); investigators drown. The framework already ships the **N1 governed alert-prioritization layer** (`engine/prioritization.py`) — an advisory `priority_score` (0-1) + `priority_explanation` stamped on every alert. #495 adds **risk-based segmentation**: declare customer segments and per-segment thresholds so low-risk-segment alerts that also score low can be **advisory-suppressed (de-prioritized)** — never auto-closed — to cut investigator load while staying audit-defensible.

## Locked decisions (and why)

1. **Declarative segments, NOT ML clustering (v1).** Segments are declared in the spec (`program.risk_segmentation`), the same way rules and thresholds already are. Rationale: the framework's hardest invariant is determinism (`test_run_is_reproducible`), the engine path is stdlib-only (sklearn lives in `[ml]`, absent from `.[dev]` unit CI), and a compliance ledger needs every suppression to be explainable and reproducible. The roadmap's "risk-based segmentation" is satisfied by declarative per-segment thresholds layered over the **already-ML** priority score. ML-discovered segments are a later enhancement (out of scope; YAGNI).

2. **Flag-on-alert, advisory only — never auto-close.** A new pure function `stamp_suppression` adds a `suppression` dict to each eligible alert (mirroring how N1 adds `priority_score`). It NEVER removes the alert, changes its disposition/queue/open-close state, or deletes keys. The rule-based alert still lands in `alerts/<rule>.jsonl` and the hash-chained ledger. Suppression is a triage lens an investigator can override.

3. **Eligibility = segment match AND low score.** An alert is flagged `suppressed` iff (a) its customer's `customer_risk_rating` is in a declared segment's `values`, AND (b) its N1 `priority_score < segment.deprioritize_below`. **Precondition:** prioritization must be enabled (the score must exist). If prioritization is off or the score is absent, `stamp_suppression` is a no-op and records `reason="prioritization disabled"` — no silent suppression.

4. **Explainable + reversible + deterministic.** The `suppression` flag carries `{applied, segment_id, reason, threshold, score, reversible: true}`. Pure function: no clock, no random, no I/O — same inputs → identical output. A frozen, manifest-pinned `suppression_report.json` summarizes counts by segment + by rule, with masked top examples (honours `AML_PII_MASKING` exactly like `priority_report`).

5. **Surface on existing Pillar-5 pages (no new page in v1).** Triage Queue (page 52) shows the suppression flag + segment as a column and an "advisory — overridable" caption; FP Analysis (page 45) shows a suppression summary. Avoids a speculative new page (YAGNI).

## Spec shape

```python
class RiskSegment(_Base):
    id: str = Field(min_length=1)
    field: str = "customer_risk_rating"        # customer attribute to match on
    values: list[str] = Field(min_length=1)    # risk-rating values in this segment
    deprioritize_below: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: str = Field(min_length=1)       # audit: why this segment de-prioritizes
    owner: str = Field(min_length=1)           # audit: who owns the policy

class RiskSegmentation(_Base):
    enabled: bool = False
    segments: list[RiskSegment] = Field(default_factory=list)

# Program gains: risk_segmentation: RiskSegmentation | None = None
```
Mirrors `ProgramPrioritization`: optional, off by default, backward-compatible (every existing spec validates unchanged). Update BOTH `spec/models.py` AND `schema/aml-spec.schema.json`.

## Engine

```python
# engine/suppression.py  (pure, stdlib + dataclass/pydantic, deterministic)
@dataclass(frozen=True)
class SuppressionResult:
    applied: bool
    segment_id: str | None
    reason: str
    threshold: float | None
    score: float | None

def stamp_suppression(rule, alerts, segmentation_cfg, customer_risk) -> None:
    """Add an advisory `suppression` dict to each alert. No-op when cfg is
    None/disabled or prioritization didn't run. Never removes keys, never
    auto-closes. `customer_risk`: {customer_id -> risk_rating} from the run."""

def build_suppression_report(alerts_by_rule, *, enabled, mask_customer_id) -> SuppressionReport:
    """Frozen, manifest-pinned summary: counts by segment + by rule, masked
    top examples. Mirrors build_priority_report."""
```
Runner integration (`engine/runner.py`): resolve `program.risk_segmentation` once; build `customer_risk` map from the customer table; after `stamp_priority(...)`, call `stamp_suppression(...)`; after the run, write `suppression_report.json` and pin `suppression_report_hash` in the manifest. Determinism contract unchanged.

## Governance invariants (carried from N1)
Advisory only · never auto-close · explainable (segment + reason + threshold + score) · reversible (overridable flag) · deterministic (hashes match) · evidenced (manifest-pinned + ledger) · PII-safe (masked report under `AML_PII_MASKING`).

## Out of scope (v1)
ML-discovered/clustered segments; separate `suppression_decision` ledger event (flag-on-alert suffices); auto-close of any kind; per-rule segment overrides; a dedicated dashboard page.

## Surfaces to update
`spec/models.py` + `schema/aml-spec.schema.json`; `engine/suppression.py` + `engine/runner.py`; dashboard pages 52 + 45; tests (`test_suppression.py` + runner determinism); docs (`spec-reference.md`, new `how-to/configure-risk-segmentation.md`, `CLAUDE.md`, `dashboard-tour.md`, `progress.md`). One example spec gains an illustrative `risk_segmentation` block.
