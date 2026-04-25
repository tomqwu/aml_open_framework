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
        # Board-level reports exist? Multiple audiences covered?
        "Governance & Culture": 3 if n_audiences >= 3 else (2 if n_reports > 0 else 1),
        # Rules with diverse tags + coverage metric?
        "Risk Assessment": min(2 + (1 if n_rules >= 4 else 0) + (1 if has_metrics else 0), 4),
        # Customer contract with risk_rating + EDD fields?
        "CDD / KYC": 2 + (1 if n_contracts >= 2 else 0) + (1 if has_edd_fields else 0),
        # Active rules across multiple logic types.
        "Transaction Monitoring": min(1 + len(rule_types) + (1 if n_rules >= 6 else 0), 5),
        # list_match rules exist? (sanctions screening)
        "Sanctions Screening": 3 if has_list_match else 1,
        # Queues with SLAs and escalation chains.
        "Case Management": min(2 + n_queues // 2, 4),
        # Regulator form configured?
        "SAR / STR Filing": 3 if has_sar else 2,
        # Spec-driven + deterministic + evidence trail + ML scoring.
        "Technology & Data": 4 + (1 if has_python_ref else 0),
        # No training module in spec — always 2.
        "Training & Awareness": 2,
        # Retention policy + reproducible runs.
        "Independent Testing": 3 if has_retention else 2,
        # Metrics + audience-specific reports.
        "Regulatory Engagement": min(
            2 + (1 if has_metrics else 0) + (1 if n_audiences >= 4 else 0), 4
        ),
        # Quality checks declared on data contracts.
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


# ---------------------------------------------------------------------------
# Regulatory Framework Alignment
# ---------------------------------------------------------------------------

FATF_MAPPING = [
    {
        "rec": "R.1",
        "title": "Risk Assessment",
        "spec_element": "program + rules + risk_rating",
        "status": "mapped",
        "notes": "Risk assessment through spec-driven rule coverage analysis.",
    },
    {
        "rec": "R.10",
        "title": "Customer Due Diligence",
        "spec_element": "data_contracts.customer",
        "status": "mapped",
        "notes": "CDD data contract with risk_rating and KYC fields.",
    },
    {
        "rec": "R.11",
        "title": "Record Keeping",
        "spec_element": "retention_policy + audit ledger",
        "status": "mapped",
        "notes": "5-year retention, immutable audit ledger.",
    },
    {
        "rec": "R.13",
        "title": "Correspondent Banking",
        "spec_element": "rules (high_risk_jurisdiction)",
        "status": "partial",
        "notes": "Geographic risk rules; full correspondent banking requires EDD.",
    },
    {
        "rec": "R.15",
        "title": "New Technologies",
        "spec_element": "spec-driven architecture",
        "status": "mapped",
        "notes": "Version-controlled, reproducible, auditable automation.",
    },
    {
        "rec": "R.19",
        "title": "Higher-Risk Countries",
        "spec_element": "rules.high_risk_jurisdiction",
        "status": "mapped",
        "notes": "Enhanced monitoring for FATF grey/black list jurisdictions.",
    },
    {
        "rec": "R.20",
        "title": "Suspicious Transaction Reporting",
        "spec_element": "reporting.forms + workflow",
        "status": "mapped",
        "notes": "STR/SAR workflow with SLAs and evidence assembly.",
    },
    {
        "rec": "R.21",
        "title": "Tipping Off",
        "spec_element": "workflow.queues (access control)",
        "status": "partial",
        "notes": "Queue-based access; full tipping-off prevention needs RBAC.",
    },
    {
        "rec": "R.26",
        "title": "Regulation and Supervision of FIs",
        "spec_element": "metrics + reports",
        "status": "mapped",
        "notes": "Regulator-ready reports with RAG indicators.",
    },
    {
        "rec": "R.40",
        "title": "International Cooperation",
        "spec_element": "regulator_mapping",
        "status": "partial",
        "notes": "Multi-jurisdiction spec support; actual cooperation is operational.",
    },
]

# --- US: FinCEN BSA Pillars ---
FINCEN_BSA_PILLARS = [
    {
        "pillar": 1,
        "name": "Internal Controls",
        "spec_element": "workflow + rules + audit ledger",
        "status": "mapped",
        "notes": "Spec-driven controls with deterministic execution and evidence trail.",
    },
    {
        "pillar": 2,
        "name": "Independent Testing",
        "spec_element": "deterministic runs + hash verification",
        "status": "mapped",
        "notes": "Any run can be re-executed and output hashes compared.",
    },
    {
        "pillar": 3,
        "name": "BSA/AML Compliance Officer",
        "spec_element": "program.owner",
        "status": "mapped",
        "notes": "Named owner in spec; metric owners provide accountability chain.",
    },
    {
        "pillar": 4,
        "name": "Training",
        "spec_element": "(roadmap item)",
        "status": "gap",
        "notes": "Training module not yet in spec; planned for Phase 3.",
    },
    {
        "pillar": 5,
        "name": "Customer Due Diligence",
        "spec_element": "data_contracts.customer",
        "status": "mapped",
        "notes": "Customer data contract with risk_rating and country.",
    },
    {
        "pillar": 6,
        "name": "Risk Assessment (Proposed April 2026)",
        "spec_element": "metrics + coverage",
        "status": "partial",
        "notes": "Typology coverage and risk metrics provide programmatic risk assessment.",
    },
]

# --- CA: PCMLTFA Five Pillars (PCMLTFR s.71) ---
PCMLTFA_PILLARS = [
    {
        "pillar": 1,
        "name": "Compliance Officer (PCMLTFR s.71(1)(a))",
        "spec_element": "program.owner",
        "status": "mapped",
        "notes": "Named Chief Compliance Officer in spec; identity reportable to FINTRAC.",
    },
    {
        "pillar": 2,
        "name": "Written Policies & Procedures (PCMLTFR s.71(1)(b))",
        "spec_element": "aml.yaml spec + workflow + rules",
        "status": "mapped",
        "notes": "The spec IS the written policy — versioned, reviewed via PR, machine-enforceable.",
    },
    {
        "pillar": 3,
        "name": "Risk Assessment (PCMLTFR s.71(1)(c))",
        "spec_element": "rules + risk_rating + metrics",
        "status": "mapped",
        "notes": "ML/TF risk factors assessed across customers, products, geographies, channels.",
    },
    {
        "pillar": 4,
        "name": "Ongoing Compliance Training (PCMLTFR s.71(1)(d))",
        "spec_element": "(roadmap item)",
        "status": "gap",
        "notes": "Training module not yet in spec; planned for Phase 3.",
    },
    {
        "pillar": 5,
        "name": "Two-Year Effectiveness Review (PCMLTFR s.71(1)(e))",
        "spec_element": "deterministic runs + hash verification + audit ledger",
        "status": "mapped",
        "notes": "Independent review via deterministic re-execution and output hash comparison.",
    },
]

# --- CA: OSFI Guideline B-8 Principles ---
OSFI_B8_PRINCIPLES = [
    {
        "principle": "Board & Senior Management Oversight",
        "spec_element": "program.owner + reports (svp/vp)",
        "status": "mapped",
        "notes": "Board-level reporting via SVP exec brief; named program owner.",
    },
    {
        "principle": "Risk-Based Approach (ERM Integration)",
        "spec_element": "severity + risk_rating + thresholds",
        "status": "mapped",
        "notes": "Risk-based rule severity, customer risk ratings, RAG-banded metrics.",
    },
    {
        "principle": "Automated Transaction Monitoring",
        "spec_element": "rules + engine + DuckDB execution",
        "status": "mapped",
        "notes": "Spec-driven automated monitoring with auditable SQL and evidence trail.",
    },
    {
        "principle": "Correspondent Banking Due Diligence",
        "spec_element": "rules.high_risk_jurisdiction",
        "status": "partial",
        "notes": "Geographic risk rules cover high-risk jurisdictions; full correspondent DD is operational.",
    },
    {
        "principle": "New Product/Technology Risk Assessment",
        "spec_element": "spec-driven architecture",
        "status": "mapped",
        "notes": "New rules go through spec PR review before deployment.",
    },
    {
        "principle": "Sanctions Screening Integration",
        "spec_element": "(roadmap item)",
        "status": "gap",
        "notes": "Sanctions screening (Criminal Code, SEMA, UNA) planned for Phase 3.",
    },
    {
        "principle": "Internal Audit Independence",
        "spec_element": "deterministic runs + audit ledger",
        "status": "mapped",
        "notes": "Independent validation via deterministic re-execution.",
    },
    {
        "principle": "Compliance Culture & Whistleblower",
        "spec_element": "program + training (roadmap)",
        "status": "partial",
        "notes": "Program structure in place; culture/whistleblower mechanisms are operational.",
    },
]

# --- EU: AMLD6 Key Requirements ---
AMLD6_REQUIREMENTS = [
    {
        "article": "Art. 8",
        "name": "Risk Assessment",
        "spec_element": "rules + risk_rating + metrics",
        "status": "mapped",
        "notes": "Risk-based approach implemented via spec-driven rule severity and customer risk ratings.",
    },
    {
        "article": "Art. 11-14",
        "name": "Customer Due Diligence",
        "spec_element": "data_contracts.customer + KYC fields",
        "status": "mapped",
        "notes": "CDD data contract with risk_rating, PEP status, and EDD review tracking.",
    },
    {
        "article": "Art. 18-18a",
        "name": "Enhanced Due Diligence",
        "spec_element": "rules.high_risk_jurisdiction + pep_screening",
        "status": "mapped",
        "notes": "EDD triggered for high-risk third countries and PEPs.",
    },
    {
        "article": "Art. 20-23",
        "name": "PEP Requirements",
        "spec_element": "rules.pep_screening",
        "status": "mapped",
        "notes": "PEP screening rule with EDD trigger and source-of-wealth evidence.",
    },
    {
        "article": "Art. 30",
        "name": "Beneficial Ownership",
        "spec_element": "data_contracts.customer (beneficial_ownership)",
        "status": "partial",
        "notes": "Customer data contract supports BO fields; registry integration is roadmap.",
    },
    {
        "article": "Art. 50",
        "name": "Suspicious Transaction Reporting",
        "spec_element": "reporting.forms.EU_STR + workflow",
        "status": "mapped",
        "notes": "STR filing workflow with SLAs, narrative generation, and evidence assembly.",
    },
    {
        "article": "Art. 46",
        "name": "Record Keeping (5 years)",
        "spec_element": "retention_policy",
        "status": "mapped",
        "notes": "5-year retention for all transaction, customer, and case records.",
    },
]

WOLFSBERG_MAPPING = [
    {
        "principle": "Risk-Based Approach",
        "spec_element": "severity + risk_rating + thresholds",
        "status": "mapped",
    },
    {
        "principle": "Customer Identification",
        "spec_element": "data_contracts.customer",
        "status": "mapped",
    },
    {"principle": "Monitoring", "spec_element": "rules + engine + metrics", "status": "mapped"},
    {"principle": "Reporting", "spec_element": "reporting.forms + reports", "status": "mapped"},
    {
        "principle": "Record Keeping",
        "spec_element": "retention_policy + audit ledger",
        "status": "mapped",
    },
    {"principle": "Training", "spec_element": "(roadmap item)", "status": "gap"},
    {"principle": "Organization", "spec_element": "program + workflow.queues", "status": "mapped"},
    {
        "principle": "AI/ML Governance",
        "spec_element": "python_ref (model_id, model_version)",
        "status": "partial",
    },
]


def get_framework_tabs(jurisdiction: str) -> list[dict[str, Any]]:
    """Return the framework alignment tabs appropriate for the jurisdiction."""
    tabs = [{"label": "FATF Recommendations", "data": FATF_MAPPING, "type": "fatf"}]
    if jurisdiction == "CA":
        tabs.append({"label": "PCMLTFA Pillars", "data": PCMLTFA_PILLARS, "type": "pillars"})
        tabs.append(
            {"label": "OSFI Guideline B-8", "data": OSFI_B8_PRINCIPLES, "type": "principles"}
        )
    elif jurisdiction == "EU":
        tabs.append({"label": "AMLD6 Requirements", "data": AMLD6_REQUIREMENTS, "type": "pillars"})
    else:
        tabs.append({"label": "FinCEN BSA Pillars", "data": FINCEN_BSA_PILLARS, "type": "pillars"})
    tabs.append({"label": "Wolfsberg Principles", "data": WOLFSBERG_MAPPING, "type": "principles"})
    return tabs


# ---------------------------------------------------------------------------
# Transformation Roadmap (jurisdiction-aware)
# ---------------------------------------------------------------------------


def get_roadmap_phases(jurisdiction: str) -> list[dict[str, Any]]:
    """Return roadmap phases tailored to jurisdiction."""
    regulator = "FINTRAC / OSFI" if jurisdiction == "CA" else "FinCEN"
    frameworks = "PCMLTFA, OSFI B-8, FATF" if jurisdiction == "CA" else "FinCEN BSA, FATF"
    exam_label = "FINTRAC / OSFI exam" if jurisdiction == "CA" else "regulatory exam"

    return [
        {
            "phase": "Phase 1: Assessment",
            "start_week": 1,
            "end_week": 4,
            "color": "#3b82f6",
            "status": "complete",
            "milestones": [
                "Current-state program assessment across 12 dimensions",
                f"Gap analysis against {frameworks}, Wolfsberg",
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
                f"Evidence bundle generation for {regulator} readiness",
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
                f"Full {exam_label} automation",
            ],
            "deliverables": [
                "Sub-second alert generation for sanctions and fraud",
                "Model performance dashboards with drift detection",
                "Automated exam package generation",
                "Program maturity score at Level 4+ across all dimensions",
            ],
        },
    ]


# Legacy alias — used by pages that haven't switched to get_roadmap_phases() yet.
ROADMAP_PHASES = get_roadmap_phases("US")


# ---------------------------------------------------------------------------
# Industry Benchmarks (for context in demo)
# ---------------------------------------------------------------------------

INDUSTRY_BENCHMARKS = {
    "false_positive_rate": {
        "industry_avg": 0.95,
        "best_in_class": 0.70,
        "note": "Industry average FP rate is 95%+; AI/ML can reduce to 70%.",
    },
    "alert_to_sar_rate": {
        "industry_avg": 0.05,
        "best_in_class": 0.15,
        "note": "Target 10-15% conversion; below 5% suggests over-alerting.",
    },
    "sla_compliance": {
        "industry_avg": 0.85,
        "best_in_class": 0.98,
        "note": "Regulatory expectation is >95% within defined SLAs.",
    },
    "typology_coverage": {
        "industry_avg": 0.60,
        "best_in_class": 0.95,
        "note": "100% of declared typologies should have active detection.",
    },
    "detection_rate_pct": {
        "industry_avg": 0.02,
        "best_in_class": 0.10,
        "note": "McKinsey: banks detect only ~2% of global illicit flows.",
    },
}
