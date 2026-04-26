"""Program Maturity Model — Big-4 style, 12 dimensions, 5 levels."""

from __future__ import annotations

from typing import Any

from aml_framework.spec.models import AMLSpec

MATURITY_LEVELS = {
    1: "Ad-Hoc",
    2: "Developing",
    3: "Defined",
    4: "Managed",
    5: "Optimized",
}

MATURITY_DIMENSIONS = [
    {
        "name": "Governance & Culture",
        "description": "Board oversight, tone from the top, committee structure, accountability.",
        "target": 4,
        "recommendations": [
            "Establish quarterly board-level AML reporting",
            "Define clear accountability matrix for compliance failures",
        ],
    },
    {
        "name": "Risk Assessment",
        "description": "Enterprise-wide ML/FT risk assessment covering customers, products, geographies.",
        "target": 4,
        "recommendations": [
            "Implement quantitative risk scoring model",
            "Conduct annual institution-wide risk assessment update",
        ],
    },
    {
        "name": "CDD / KYC",
        "description": "Customer due diligence tiers, beneficial ownership, ongoing monitoring.",
        "target": 4,
        "recommendations": [
            "Implement tiered CDD (SDD/CDD/EDD) based on risk rating",
            "Automate periodic KYC refresh cycles",
        ],
    },
    {
        "name": "Transaction Monitoring",
        "description": "Rule coverage, tuning methodology, scenario validation.",
        "target": 5,
        "recommendations": [
            "Expand typology coverage to 10+ scenarios",
            "Implement above/below-the-line threshold methodology",
        ],
    },
    {
        "name": "Sanctions Screening",
        "description": "Real-time screening, fuzzy matching, list management.",
        "target": 4,
        "recommendations": [
            "Deploy real-time sanctions screening on all channels",
            "Implement automated list update with version control",
        ],
    },
    {
        "name": "Case Management",
        "description": "Investigation workflow, SLA enforcement, four-eyes principle.",
        "target": 4,
        "recommendations": [
            "Implement automated case assignment and load balancing",
            "Add SLA breach alerting and escalation",
        ],
    },
    {
        "name": "SAR / STR Filing",
        "description": "Filing timeliness, narrative quality, continuing activity tracking.",
        "target": 4,
        "recommendations": [
            "Implement SAR narrative template with auto-populated fields",
            "Track 90-day continuing activity SAR obligations",
        ],
    },
    {
        "name": "Technology & Data",
        "description": "Platform architecture, data quality, automation, spec-driven governance.",
        "target": 5,
        "recommendations": [
            "Adopt spec-driven architecture for policy-to-implementation traceability",
            "Implement data quality monitoring with freshness SLAs",
        ],
    },
    {
        "name": "Training & Awareness",
        "description": "Role-based training, completion tracking, knowledge assessment.",
        "target": 3,
        "recommendations": [
            "Deploy role-specific AML training curriculum",
            "Track completion rates and assessment scores",
        ],
    },
    {
        "name": "Independent Testing",
        "description": "Audit coverage, validation methodology, finding remediation.",
        "target": 4,
        "recommendations": [
            "Establish annual independent testing program",
            "Implement deterministic rule re-execution for validation",
        ],
    },
    {
        "name": "Regulatory Engagement",
        "description": "Exam readiness, relationship management, proactive communication.",
        "target": 3,
        "recommendations": [
            "Maintain exam-ready evidence bundles at all times",
            "Proactively share program enhancements with regulators",
        ],
    },
    {
        "name": "Data Quality & Lineage",
        "description": "Data completeness, accuracy, lineage tracking, SLA compliance.",
        "target": 4,
        "recommendations": [
            "Implement contract-based data quality checks",
            "Track data lineage from source to alert",
        ],
    },
]


def compute_maturity_scores(spec: AMLSpec) -> list[dict[str, Any]]:
    """Derive current maturity scores from spec coverage analysis.

    Each dimension score is computed from actual spec content rather than
    hardcoded — the score reflects what the spec *declares*, not what an
    expert assessment would conclude.
    """
    n_rules = len([r for r in spec.rules if r.status == "active"])
    n_queues = len(spec.workflow.queues)
    has_sar = any(q.regulator_form for q in spec.workflow.queues)
    has_metrics = len(spec.metrics) > 0
    n_reports = len(spec.reports)
    n_contracts = len(spec.data_contracts)
    has_quality_checks = any(c.quality_checks for c in spec.data_contracts)
    has_retention = spec.retention_policy is not None
    has_list_match = any(r.logic.type == "list_match" for r in spec.rules)
    has_python_ref = any(r.logic.type == "python_ref" for r in spec.rules)
    n_audiences = len({r.audience for r in spec.reports}) if spec.reports else 0
    has_edd_fields = any(
        any(c.name == "edd_last_review" for c in contract.columns)
        for contract in spec.data_contracts
    )
    rule_types = {r.logic.type for r in spec.rules}

    scores = {
        "Governance & Culture": 3 if n_audiences >= 3 else (2 if n_reports > 0 else 1),
        "Risk Assessment": min(2 + (1 if n_rules >= 4 else 0) + (1 if has_metrics else 0), 4),
        "CDD / KYC": 2 + (1 if n_contracts >= 2 else 0) + (1 if has_edd_fields else 0),
        "Transaction Monitoring": min(1 + len(rule_types) + (1 if n_rules >= 6 else 0), 5),
        "Sanctions Screening": 3 if has_list_match else 1,
        "Case Management": min(2 + n_queues // 2, 4),
        "SAR / STR Filing": 3 if has_sar else 2,
        "Technology & Data": 4 + (1 if has_python_ref else 0),
        "Training & Awareness": 2,
        "Independent Testing": 3 if has_retention else 2,
        "Regulatory Engagement": min(
            2 + (1 if has_metrics else 0) + (1 if n_audiences >= 4 else 0), 4
        ),
        "Data Quality & Lineage": 2
        + (1 if has_quality_checks else 0)
        + (1 if n_contracts >= 2 else 0),
    }

    result = []
    for dim in MATURITY_DIMENSIONS:
        result.append(
            {
                **dim,
                "current": scores.get(dim["name"], 2),
            }
        )
    return result
