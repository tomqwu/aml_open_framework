# Cyber-enabled fraud example spec — pig-butchering / authorised-push-payment

A typology-focused AML spec composing the framework's existing primitives
into detection of **pig-butchering / relationship-investment scams**, the
single fastest-growing cyber-enabled fraud typology of 2025-2026.

## Industry signal (why this spec, in 2026)

| Signal | Date | Implication |
|---|---|---|
| FATF "Cyber-Enabled Fraud" plenary paper | Feb 2026 | Pig-butchering named top-tier global threat |
| FBI IC3 report (US losses $5.8B in 2024) | Mar 2025 | US victims dominate global volume |
| FinCEN reissues FIN-2023-Alert005 | 2026 | "PIG BUTCHERING" added as SAR Advisory Key Term |
| Singapore +61% / UK 40% of all crime | 2025-2026 | Volume is no longer fringe |
| FinCEN Section 311 — Huione Group | May 2025 | Primary money-laundering concern; pig-butchering proceeds nexus |

No other open-source AML framework ships a pig-butchering reference rule
pack today.

## Rules

| Rule | Logic | What it catches |
|---|---|---|
| `pig_butchering_payout_fan` | `network_pattern` (PR #49 subgraph capture) | Customer outbound → ≥3 distinct beneficiaries → 1-2 on-ramp clusters |
| `ramp_up_then_drain` | `aggregation_window` + `tuning_grid` (PR #50) | ≥3 priming transfers (<$500) followed by drain inside 14 days |
| `pig_butchering_nexus_screening` | `list_match` (fuzzy) | Counterparty name on the bank's Section 311 / Huione-nexus list |

## Composing existing PRs

- **PR #46 pKYC** — wire the bank's CDD pipeline to write `new_beneficiary` events; the `ramp_up_then_drain` rule flags one when a customer suddenly drains to a brand-new beneficiary.
- **PR #45 narrative drafter** — every fired alert produces a draft STR with the FATF/FinCEN citations baked in (no hand-written narrative).
- **PR #49 network-pattern explainability** — the payout-fan alert includes a Mermaid subgraph showing the matched cluster.
- **PR #43 goAML / PR #48 AMLA STR exporters** — final STR/SAR is one CLI command away.

## Quick start

```bash
# Run the spec end-to-end on synthetic data
aml run examples/cyber_enabled_fraud/aml.yaml --seed 42

# Tune the ramp-up-then-drain thresholds
aml tune examples/cyber_enabled_fraud/aml.yaml --rule ramp_up_then_drain

# Draft an STR for a fired case
aml draft-narrative examples/cyber_enabled_fraud/aml.yaml CASE_ID --backend template

# Export to FinCEN SAR (goAML format)
aml export-goaml examples/cyber_enabled_fraud/aml.yaml --report-code SAR
```

## What's NOT in scope

- **APP / authorised-push-payment fraud** (UK PSR mandates reimbursement).
  Sibling typology — clean follow-up after this lands. Bundling them would
  double the effort without doubling the user signal per the Round-4
  research scan.
- **Live counterparty intelligence** — the `pig_butchering_nexus.csv` ships
  with a placeholder "Huione Group" entry. Operators wire their full
  Section 311 + ComplyAdvantage / Chainalysis attribution feeds via
  `aml sanctions-sync` (PR #44) once provisioned.

## Sources

- [FATF Cyber-Enabled Fraud paper (Feb 2026)](https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Cyber-Enabled-Fraud%E2%80%93Digitalisation-and-ML-TF-PF-Risks.pdf.coredownload.inline.pdf)
- [FinCEN: Dating or Defrauding (2026 reminder)](https://www.fincen.gov/news/news-releases/dating-or-defrauding-2026)
- [FinCEN SAR Advisory Key Terms](https://www.fincen.gov/resources/suspicious-activity-report-sar-advisory-key-terms)
- [FBI IC3 2024 Internet Crime Report](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf)
- [FinCEN Section 311 — Huione Group (May 2025)](https://www.fincen.gov/news/news-releases/treasury-issues-section-311-finding-huione-group)
