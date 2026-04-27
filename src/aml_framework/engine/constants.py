"""Canonical names for engine events and workflow queues.

These strings are written to `decisions.jsonl` (the audit log) and read back
by the dashboard and the metrics engine. Keeping them centralised here means
a typo or rename in one place can't drift past type-checking — every caller
that imports from this module catches the change.
"""

from __future__ import annotations


class Event:
    """Decision-event type constants. Written to `decisions.jsonl["event"]`."""

    CASE_OPENED = "case_opened"
    ESCALATED = "escalated"
    ESCALATED_TO_STR = "escalated_to_str"
    CLOSED = "closed"
    RULE_FAILED = "rule_failed"
    MANUAL_REVIEW = "manual_review"
    NARRATIVE_REVIEW = "narrative_review"  # analyst accepted/amended/rejected a draft
    PKYC_REVIEW = "pkyc_review"  # analyst acted on a pKYC trigger
    TUNING_RUN = "tuning_run"  # `aml tune` swept thresholds for a rule


class Queue:
    """Workflow queue id constants used by engine routing."""

    CLOSED_NO_ACTION = "closed_no_action"
    L2_INVESTIGATOR = "l2_investigator"
    STR_FILING = "str_filing"
    SAR_FILING = "sar_filing"
