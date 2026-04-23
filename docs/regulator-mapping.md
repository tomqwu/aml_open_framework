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

| Concern                         | Authority / clause                     | Spec primitive                          |
|---------------------------------|----------------------------------------|-----------------------------------------|
| STR filing                      | PCMLTFA s.7                            | `reporting.forms.FINTRAC_STR`           |
| LCTR (large cash)               | PCMLTFR s.12                           | `reporting.forms.FINTRAC_LCTR`          |
| EFTR (electronic funds)         | PCMLTFR s.28                           | `reporting.forms.FINTRAC_EFTR`          |
| Know-your-client                | PCMLTFR Part 4                         | `data_contracts.customer`               |
| Recordkeeping (5 years)         | PCMLTFR s.69                           | `retention_policy.evidence: 5y`         |

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
