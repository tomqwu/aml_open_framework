# How to produce an AMLA RTS effectiveness report

**Deadline: AMLA submits final-draft RTS to the European Commission by 2026-07-10.**

EU obliged entities (credit institutions, payment institutions, e-money institutions, crypto-asset service providers, and other AMLA-supervised obliged entities) must demonstrate their AML/CFT programs satisfy the three regulatory technical standards:

| RTS | Authority | Article | Due |
|-----|-----------|---------|-----|
| CDD RTS | AMLA / AMLR | Art. 28(1) | 2026-07-10 |
| Business-relationships RTS | AMLA / AMLR | Art. 19(9) | 2026-07-10 |
| Pecuniary-sanctions RTS | AMLA / AMLD6 | Art. 53(10) | 2026-07-10 |

The `aml amla-effectiveness-report` command generates the evidence pack in one command.

---

## Prerequisites

- An EU-jurisdiction spec (e.g. `examples/eu_bank/aml.yaml`)
- Rules annotated with AMLA RTS citations in `regulation_refs` (the `eu_bank` spec ships these)
- *(Optional)* A completed engine run for funnel metrics

---

## Step 1 — Annotate your spec's rules

Each rule that satisfies an AMLA RTS obligation should carry the relevant citation in its `regulation_refs`:

```yaml
rules:
  - id: structuring_cash
    name: Cash structuring below EUR 15,000 threshold
    severity: high
    regulation_refs:
      - citation: "AMLD6 Art. 50"
        description: "Suspicious transaction reporting obligation."
      - citation: "AMLR Art. 28(1)"
        description: "CDD RTS — demonstrates effectiveness of transaction monitoring."
```

Use the pattern strings the framework recognises:

| Cite this | To satisfy |
|-----------|-----------|
| `AMLR Art. 28(1)` | CDD RTS — Art. 28(1) |
| `AMLR Art. 19(9)` | Business-relationships RTS — Art. 19(9) |
| `AMLD6 Art. 53(10)` | Pecuniary-sanctions RTS — Art. 53(10) |

The `eu_bank` example spec already carries these citations on all relevant rules.

---

## Step 2 — Run the effectiveness report

**Citation-coverage only** (no run required — spec analysis alone):

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml \
    --out amla_effectiveness_report.json
```

**With funnel metrics** (after `aml run`):

```bash
aml run examples/eu_bank/aml.yaml --seed 42

aml amla-effectiveness-report examples/eu_bank/aml.yaml \
    --out amla_effectiveness_report.json \
    --markdown amla_effectiveness_report.md \
    --lei 529900T8BM49AURSDO55 \
    --entity-type credit_institution \
    --home-state DE \
    --period-start 2026-01-01 \
    --period-end 2026-06-30
```

The `--markdown` flag writes a pipe-formatted table ready for the model-risk committee report.

---

## Step 3 — Review the output

The JSON report has two top-level sections:

```json
{
  "spec_program": "eu_bank_aml",
  "as_of": "2026-06-09T12:00:00+00:00",
  "rts_version": "2026-07-draft",
  "rts_coverage": [
    {
      "article_id": "AMLR_28_1",
      "citation": "AMLR Art. 28(1)",
      "rts_name": "CDD RTS",
      "rule_count": 4,
      "rule_ids": ["high_risk_jurisdiction", "pep_screening", "rapid_movement_sepa", "structuring_cash"],
      "status": "covered"
    },
    ...
  ],
  "funnel": {
    "totals": { "alerts": 42, "cases": 42, "str_filed": 8, ... },
    "rules": [ ... ]
  }
}
```

Coverage statuses:

| Status | Meaning |
|--------|---------|
| `covered` | ≥ 2 rules carry this RTS citation |
| `partial` | 1 rule carries this RTS citation |
| `gap` | No rule references this article — add citations or create a compensating rule |

---

## Step 4 — Dashboard

Open the Framework Alignment page (page 8). For EU specs a new **AMLA RTS Coverage** tab appears alongside the AMLD6 and FATF tabs, showing the per-article status inline.

---

## Viewing the live EU spec

```bash
aml validate examples/eu_bank/aml.yaml
aml dashboard examples/eu_bank/aml.yaml
```

---

## See also

- [`docs/jurisdictions.md`](../jurisdictions.md) — EU section with AMLA operational timeline
- [`aml outcomes-pack`](../api-reference.md) — full AMLA RTS draft 2026-02 funnel JSON
- [AMLA portal — RTS consultations](https://www.amla.europa.eu/policy/public-consultations/)
