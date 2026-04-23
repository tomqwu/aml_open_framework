"""Consulting-grade content: maturity model, framework alignment, roadmap."""

from __future__ import annotations

from typing import Any

from aml_framework.spec.models import AMLSpec

# ---------------------------------------------------------------------------
# Program Maturity Model (Big-4 style, 12 dimensions, 5 levels)
# ---------------------------------------------------------------------------

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
    """Derive current maturity scores from spec coverage analysis."""
    n_rules = len([r for r in spec.rules if r.status == "active"])
    n_queues = len(spec.workflow.queues)
    has_sar = any(q.regulator_form for q in spec.workflow.queues)
    has_metrics = len(spec.metrics) > 0
    n_contracts = len(spec.data_contracts)
    has_quality_checks = any(c.quality_checks for c in spec.data_contracts)
    has_retention = spec.retention_policy is not None

    scores = {
        "Governance & Culture": 3,
        "Risk Assessment": 2 if n_rules < 4 else 3,
        "CDD / KYC": 2 if n_contracts < 2 else 3,
        "Transaction Monitoring": min(2 + n_rules // 2, 5),
        "Sanctions Screening": 1,
        "Case Management": 2 + min(n_queues // 2, 2),
        "SAR / STR Filing": 3 if has_sar else 2,
        "Technology & Data": 4,  # Spec-driven + deterministic + evidence trail
        "Training & Awareness": 2,
        "Independent Testing": 3 if has_retention else 2,
        "Regulatory Engagement": 2 if not has_metrics else 3,
        "Data Quality & Lineage": 3 if has_quality_checks else 2,
    }

    result = []
    for dim in MATURITY_DIMENSIONS:
        result.append({
            **dim,
            "current": scores.get(dim["name"], 2),
        })
    return result


# ---------------------------------------------------------------------------
# Regulatory Framework Alignment
# ---------------------------------------------------------------------------

FATF_MAPPING = [
    {"rec": "R.1", "title": "Risk Assessment", "spec_element": "program + rules + risk_rating",
     "status": "mapped", "notes": "Risk assessment through spec-driven rule coverage analysis."},
    {"rec": "R.10", "title": "Customer Due Diligence", "spec_element": "data_contracts.customer",
     "status": "mapped", "notes": "CDD data contract with risk_rating and KYC fields."},
    {"rec": "R.11", "title": "Record Keeping", "spec_element": "retention_policy + audit ledger",
     "status": "mapped", "notes": "5-7 year retention, immutable audit ledger."},
    {"rec": "R.13", "title": "Correspondent Banking", "spec_element": "rules (high_risk_jurisdiction)",
     "status": "partial", "notes": "Geographic risk rules; full correspondent banking requires EDD."},
    {"rec": "R.15", "title": "New Technologies", "spec_element": "spec-driven architecture",
     "status": "mapped", "notes": "Version-controlled, reproducible, auditable automation."},
    {"rec": "R.19", "title": "Higher-Risk Countries", "spec_element": "rules.high_risk_jurisdiction",
     "status": "mapped", "notes": "Enhanced monitoring for FATF grey/black list jurisdictions."},
    {"rec": "R.20", "title": "Suspicious Transaction Reporting", "spec_element": "reporting.forms + workflow",
     "status": "mapped", "notes": "SAR workflow with SLAs and evidence assembly."},
    {"rec": "R.21", "title": "Tipping Off", "spec_element": "workflow.queues (access control)",
     "status": "partial", "notes": "Queue-based access; full tipping-off prevention needs RBAC."},
    {"rec": "R.26", "title": "Regulation and Supervision of FIs", "spec_element": "metrics + reports",
     "status": "mapped", "notes": "Regulator-ready reports with RAG indicators."},
    {"rec": "R.40", "title": "International Cooperation", "spec_element": "regulator_mapping",
     "status": "partial", "notes": "Multi-jurisdiction spec support; actual cooperation is operational."},
]

FINCEN_BSA_PILLARS = [
    {"pillar": 1, "name": "Internal Controls", "spec_element": "workflow + rules + audit ledger",
     "status": "mapped", "notes": "Spec-driven controls with deterministic execution and evidence trail."},
    {"pillar": 2, "name": "Independent Testing", "spec_element": "deterministic runs + hash verification",
     "status": "mapped", "notes": "Any run can be re-executed and output hashes compared."},
    {"pillar": 3, "name": "BSA/AML Compliance Officer", "spec_element": "program.owner",
     "status": "mapped", "notes": "Named owner in spec; metric owners provide accountability chain."},
    {"pillar": 4, "name": "Training", "spec_element": "(roadmap item)",
     "status": "gap", "notes": "Training module not yet in spec; planned for Phase 3."},
    {"pillar": 5, "name": "Customer Due Diligence", "spec_element": "data_contracts.customer",
     "status": "mapped", "notes": "Customer data contract with risk_rating and country."},
    {"pillar": 6, "name": "Risk Assessment (Proposed April 2026)", "spec_element": "metrics + coverage",
     "status": "partial", "notes": "Typology coverage and risk metrics provide programmatic risk assessment."},
]

WOLFSBERG_MAPPING = [
    {"principle": "Risk-Based Approach", "spec_element": "severity + risk_rating + thresholds",
     "status": "mapped"},
    {"principle": "Customer Identification", "spec_element": "data_contracts.customer",
     "status": "mapped"},
    {"principle": "Monitoring", "spec_element": "rules + engine + metrics",
     "status": "mapped"},
    {"principle": "Reporting", "spec_element": "reporting.forms + reports",
     "status": "mapped"},
    {"principle": "Record Keeping", "spec_element": "retention_policy + audit ledger",
     "status": "mapped"},
    {"principle": "Training", "spec_element": "(roadmap item)",
     "status": "gap"},
    {"principle": "Organization", "spec_element": "program + workflow.queues",
     "status": "mapped"},
    {"principle": "AI/ML Governance", "spec_element": "python_ref (model_id, model_version)",
     "status": "partial"},
]


# ---------------------------------------------------------------------------
# Transformation Roadmap
# ---------------------------------------------------------------------------

ROADMAP_PHASES = [
    {
        "phase": "Phase 1: Assessment",
        "start_week": 1,
        "end_week": 4,
        "color": "#3b82f6",
        "status": "complete",
        "milestones": [
            "Current-state program assessment across 12 dimensions",
            "Gap analysis against FATF, FinCEN BSA, Wolfsberg",
            "Risk assessment of customer, product, and geographic exposure",
            "Prioritized remediation backlog",
        ],
        "deliverables": [
            "Maturity scorecard with dimension-level scores",
            "Gap register with severity and remediation owners",
            "Risk-ranked backlog of detection improvements",
        ],
    },
    {
        "phase": "Phase 2: Foundation",
        "start_week": 5,
        "end_week": 16,
        "color": "#8b5cf6",
        "status": "in_progress",
        "milestones": [
            "Spec-driven framework deployment with CI/CD pipeline",
            "Core typology catalogue (6+ rules across major risk categories)",
            "Audit trail activation with deterministic re-execution",
            "Role-specific reporting framework (SVP through developer)",
            "Evidence bundle generation for regulator readiness",
        ],
        "deliverables": [
            "aml.yaml with validated rules and metrics",
            "Automated evidence bundle with hash verification",
            "Control matrix mapping rules to regulation citations",
            "Audience-specific dashboards and reports",
        ],
    },
    {
        "phase": "Phase 3: Advanced Analytics",
        "start_week": 17,
        "end_week": 30,
        "color": "#ec4899",
        "status": "planned",
        "milestones": [
            "Rule tuning using above/below-the-line methodology",
            "ML-scored alert prioritization (python_ref integration)",
            "Network analysis for relationship-based detection",
            "Enhanced CDD/EDD automation",
        ],
        "deliverables": [
            "Tuned rules with documented false positive reduction",
            "ML model integration with model risk management metadata",
            "Network visualization for investigation workflows",
            "Automated KYC refresh scheduling",
        ],
    },
    {
        "phase": "Phase 4: Optimization",
        "start_week": 31,
        "end_week": 52,
        "color": "#14b8a6",
        "status": "planned",
        "milestones": [
            "Real-time transaction monitoring for critical typologies",
            "Predictive analytics for emerging risk patterns",
            "Continuous model validation and performance monitoring",
            "Full regulatory exam automation",
        ],
        "deliverables": [
            "Sub-second alert generation for sanctions and fraud",
            "Model performance dashboards with drift detection",
            "Automated exam package generation",
            "Program maturity score at Level 4+ across all dimensions",
        ],
    },
]


# ---------------------------------------------------------------------------
# Industry Benchmarks (for context in demo)
# ---------------------------------------------------------------------------

INDUSTRY_BENCHMARKS = {
    "false_positive_rate": {"industry_avg": 0.95, "best_in_class": 0.70,
                           "note": "Industry average FP rate is 95%+; AI/ML can reduce to 70%."},
    "alert_to_sar_rate": {"industry_avg": 0.05, "best_in_class": 0.15,
                          "note": "Target 10-15% conversion; below 5% suggests over-alerting."},
    "sla_compliance": {"industry_avg": 0.85, "best_in_class": 0.98,
                       "note": "Regulatory expectation is >95% within defined SLAs."},
    "typology_coverage": {"industry_avg": 0.60, "best_in_class": 0.95,
                          "note": "100% of declared typologies should have active detection."},
    "detection_rate_pct": {"industry_avg": 0.02, "best_in_class": 0.10,
                           "note": "McKinsey: banks detect only ~2% of global illicit flows."},
}
