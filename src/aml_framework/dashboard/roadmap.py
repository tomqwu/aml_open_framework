"""Transformation roadmap and industry benchmarks."""

from __future__ import annotations

from typing import Any


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
