"""Regulatory framework alignment mappings — FATF, BSA, PCMLTFA, OSFI, AMLD6, Wolfsberg."""

from __future__ import annotations

from typing import Any

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
