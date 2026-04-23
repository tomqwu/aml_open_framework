# Regulator Mapping

The framework is regulator-agnostic — jurisdictions plug in via the
`program.jurisdiction` and `program.regulator` fields in the spec, and each
rule cites its own regulation clause. This doc summarises how common regimes
map onto the spec primitives.

> Nothing here is legal advice. Verify current text with your 2nd line or
> external counsel before relying on any citation.

## United States (FinCEN, OCC, OFAC)

| Concern                         | Authority / clause                     | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| SAR filing                      | 31 CFR 1020.320                        | `reporting.forms.FinCEN_SAR`            |
| CTR filing                      | 31 CFR 1010.311                        | `reporting.forms.FinCEN_CTR`            |
| Structuring                     | 31 CFR 1010.314                        | `rules[*].regulation_refs`              |
| CIP / KYC                       | 31 CFR 1020.220                        | `data_contracts.customer` + KYC fields  |
| OFAC sanctions screening        | 31 CFR Ch. V (OFAC)                    | Rule of type `sanctions_list_match`     |
| Recordkeeping (5 years)         | 31 CFR 1010.430                        | `retention_policy.evidence: 5y`         |

## Canada (FINTRAC, OSFI)

### Core obligations

| Concern                         | Authority / clause                     | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| STR filing                      | PCMLTFA s.7                            | `reporting.forms.FINTRAC_STR`           |
| LCTR (large cash ≥ $10k CAD)   | PCMLTFR s.7(1)                         | `reporting.forms.FINTRAC_LCTR`          |
| EFTR (cross-border EFT ≥ $10k) | PCMLTFR s.12(1)                        | `reporting.forms.FINTRAC_EFTR`          |
| 24-hour aggregation rule        | PCMLTFR s.132                          | `rules[*].logic` (aggregation_window)   |
| Structuring offence             | PCMLTFA s.11.1                         | `rules.structuring_cash_deposits`       |
| Know-your-client                | PCMLTFR ss.105-120                     | `data_contracts.customer`               |
| Beneficial ownership (≥ 25%)    | PCMLTFR s.138                          | `data_contracts.customer` (KYC fields)  |
| Ongoing monitoring              | PCMLTFR s.123.1                        | `rules.unusual_volume_spike`            |
| PEP / HIO determination         | PCMLTFA s.9.3, PCMLTFR ss.121-123     | Rule of type `pep_match`                |
| Correspondent banking DD        | PCMLTFA s.9.4                          | `rules.high_risk_jurisdiction`          |
| Recordkeeping (5 years)         | PCMLTFR ss.144-145                     | `retention_policy.evidence: 5y`         |

### PCMLTFR s.71 — Five pillars of a compliance program

| Pillar | Requirement                    | Spec primitive                          |
|--------|--------------------------------|-----------------------------------------|
| 1      | Compliance Officer (s.71(1)(a))| `program.owner`                         |
| 2      | Written Policies (s.71(1)(b)) | `aml.yaml` spec (versioned, PR-reviewed)|
| 3      | Risk Assessment (s.71(1)(c))  | `metrics` + `rules` + risk_rating       |
| 4      | Training (s.71(1)(d))         | *(roadmap item)*                        |
| 5      | Effectiveness Review (s.71(1)(e))| Deterministic re-execution + hash verification |

### OSFI Guideline B-8 — Additional expectations for FRFIs

| Concern                         | B-8 section                            | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| Board & senior management oversight | B-8 s.2                            | `reports` (svp/vp audience)             |
| Automated transaction monitoring| B-8 s.3                                | `rules` + `engine` execution            |
| Enhanced DD (high-risk geo)     | B-8 s.4                                | `rules.high_risk_jurisdiction`          |
| Sanctions screening integration| B-8 s.5                                | *(roadmap item)*                        |
| Internal audit independence     | B-8 s.6                                | Audit ledger + hash verification        |

### TD Bank 2024 enforcement — gap-to-spec mapping

See [`docs/case-studies/td-2024.md`](case-studies/td-2024.md) for detailed
traceability from each TD Bank finding to the specific spec clause in
`examples/canadian_schedule_i_bank/aml.yaml` that would surface the gap.

## European Union (AMLD6, and soon AMLR / AMLA)

| Concern                         | Authority / clause                     | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| Suspicious activity reporting   | AMLD6 Art. 50                          | `reporting.forms.EU_STR`                |
| Beneficial ownership            | AMLD5 Art. 30 / AMLR                   | `data_contracts.beneficial_owner`       |
| Enhanced due diligence triggers | AMLD6 Art. 28                          | Rule tags `edd_trigger: true`           |
| Politically Exposed Persons     | AMLD6 Art. 20                          | Rule of type `pep_match`                |

## United Kingdom (FCA, NCA)

| Concern                         | Authority / clause                     | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| SAR to UKFIU                    | POCA 2002 s.330                        | `reporting.forms.UK_SAR`                |
| MLR 2017 customer DD            | MLR 2017 reg. 28                       | `data_contracts.customer`               |
| Sanctions (OFSI)                | SAMLA 2018                             | Rule of type `sanctions_list_match`     |

## Cross-regime patterns

These appear across almost every regime and are first-class in the spec:

- **Structuring / smurfing** — windowed aggregation rule. See
  `examples/community_bank/aml.yaml` for a reference implementation.
- **Rapid fund movement / pass-through** — in/out matching within a short
  window, often across counterparties.
- **Sanctions / PEP list matching** — deterministic list join with name
  fuzzing; spec records the list version.
- **Unusual activity vs. customer profile** — compare actuals to expected
  behaviour declared at onboarding.
- **Geographic risk** — transactions with high-risk jurisdictions per FATF
  grey/black lists.

## Mapping to the control matrix

When `aml generate` runs, it produces `control_matrix.md` — a table with one
row per rule, columns: `rule_id`, `severity`, `regulation_refs`, `owner`,
`last_reviewed`, `evidence_sample_path`. This is the single page most
auditors and regulators ask for first.
