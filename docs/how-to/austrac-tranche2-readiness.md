# How to stand up an AUSTRAC Tranche 2 compliant program

> **When you need this:** You are an Australian designated non-financial business or profession (DNFBP) — a law firm, accounting practice, real-estate agency, or dealer in precious metals and stones (DPMS) — and AUSTRAC Tranche 2 enforcement is effective 2026-07-01. You need to be enrolled with AUSTRAC and have a **board-approved AML/CTF program** in place. This recipe walks the minimum-viable path from nothing to a documented, board-attestable compliance program using the framework's AU example spec.
>
> **Prereqs:** `pip install -e ".[dev]"`. The bundled `examples/au_dnfbp/aml.yaml` spec (AUSTRAC Tranche 2 DNFBPs — lawyers / accountants / real-estate / precious metals). A printed or digital copy of AUSTRAC's [Tranche 2 enrolment checklist](https://www.austrac.gov.au/amlctf-reform).
>
> **Time:** ~30 min for the compliance program; a few minutes for the framework run.

AUSTRAC's stated first-cycle posture for Tranche 2 is **enforceable undertakings (EUs) over fines** — but only for firms with documented, good-faith compliance efforts. A board-approved program, even a lean one, is the material difference between an EU and an immediate penalty from day one. The framework's `examples/au_dnfbp/aml.yaml` spec was built for exactly this entity class: it covers the four DNFBP types, the two AU filing forms (SMR and TTR), and AUSTRAC-specific `regulation_refs` citations on every active rule.

---

## Steps

### 1 · Enrol with AUSTRAC

All Tranche 2 DNFBPs must enrol at the AUSTRAC enrolment portal before operating:

- Lawyers / accountants / real-estate agents / DPMS with **AML/CTF obligations** must be enrolled as of 2026-07-01.
- AUSTRAC's enrolment requires: ABN, business name, principal place of business, designated services provided, and a responsible person (your MLRO equivalent).

The framework's spec maps to the enrolment record:

```yaml
program:
  name: au_dnfbp_aml
  jurisdiction: AU
  filing_authority: AUSTRAC
  owner: compliance@yourfirm.com.au
```

`filing_authority: AUSTRAC` stamps the program as an AUSTRAC-reporting entity. `jurisdiction: AU` selects the AU synthetic data and AU-specific rule shapes.

**Sources:**
- [AUSTRAC: Enrolment for Tranche 2 reporting entities](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)
- [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform)

### 2 · Customise the spec for your DNFBP type

Open `examples/au_dnfbp/aml.yaml` and edit the `program` block for your entity:

```yaml
program:
  name: your_firm_aml          # used in run artefact filenames
  jurisdiction: AU
  filing_authority: AUSTRAC
  owner: compliance@yourfirm.com.au
  environment: prod            # or dev while you're still testing
  # Describe your designated services:
  # law firm → remove accounting / real-estate / dpms rules
  # accounting practice → remove law firm / real-estate / dpms rules
  # etc.
```

The bundled spec ships rules for all four DNFBP types — disable the rules that don't apply to your entity type by setting `status: inactive` on them.

### 3 · Validate the program

```bash
aml validate examples/au_dnfbp/aml.yaml
```

A clean pass confirms the spec is structurally valid and all cross-references (data contracts → rules → reports) are intact. Under `--strict`, an active rule missing `risk_tier` is a hard error — so the spec also forces you to declare the risk tier of every active control.

```bash
aml validate examples/au_dnfbp/aml.yaml --strict
```

If you see `WARN: active rule <id> is missing risk_tier`, add `risk_tier: low | medium | high` to the rule's block. The risk-tier declaration is the spec-side evidence that you've assessed the rule's risk profile — AUSTRAC expects documented risk assessment underpinning your program.

### 4 · Run the program engine

```bash
aml run examples/au_dnfbp/aml.yaml --seed 42
```

The engine writes a run directory under `.artifacts/run-<ts>/` containing:
- `manifest.json` — a SHA-256-pinned record of the spec version, run timestamp, and input file hashes. This is your **program activation artifact**: the manifest hash is what you attest to the board.
- `decisions.jsonl` — the append-only audit ledger (every rule evaluation + disposition).
- `cases/` — per-case evidence bundles.
- `sla_report.json`, `dq_exceptions.jsonl`, `defect_log.jsonl` — monitoring and quality artifacts.

AUSTRAC expects a documented, board-approved program. The manifest hash (`manifest.json::manifest_hash`) is the machine-readable evidence of "this program was approved in this configuration on this date." Your board resolution can reference it by hash.

### 5 · Confirm SMR and TTR filing readiness

Australia files **Suspicious Matter Reports (SMRs)** — not STRs — and **Transaction Threshold Reports (TTRs)** for cash dealings above the AUD 10,000 threshold. The AU spec maps both:

```yaml
reporting:
  forms:
    - id: SMR
      description: AUSTRAC Suspicious Matter Report
    - id: TTR
      description: AUSTRAC Transaction Threshold Report (cash ≥ AUD 10,000)
```

Generate the regulator-ready export bundle:

```bash
aml export .artifacts/run-<ts> --out au_dnfbp_audit_pack.zip
```

The ZIP carries the manifest, decisions ledger, all case packs, and the STR narratives — ready to hand to AUSTRAC or your legal counsel.

### 6 · Verify the program audit chain

```bash
aml verify-decisions .artifacts/run-<ts>
```

A passing `VERIFIED` output confirms the `decisions.jsonl` hash chain is intact. This is the integrity check AUSTRAC will expect if they inspect your evidence — the ledger can be proven untampered.

---

## Verify it worked

1. `aml validate --strict` passes with no ERRORs.
2. The run directory exists under `.artifacts/run-<ts>/` with a `manifest.json` whose `manifest_hash` is present and non-empty.
3. `aml verify-decisions` reports `VERIFIED`.
4. `au_dnfbp_audit_pack.zip` opens and contains `manifest.json`, `decisions.jsonl`, and at least one `cases/` entry.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `WARN: active rule <id> missing risk_tier` | Rule block has no `risk_tier` field | Add `risk_tier: low`, `medium`, or `high` based on your risk assessment |
| `ERROR: data contract 'txn' not found` | You pointed at the wrong spec path | Make sure you're running against `examples/au_dnfbp/aml.yaml` or a copy of it |
| SMR rules aren't firing | No transactions satisfy the SMR conditions in synthetic data | Run with `--seed 42`; the AU spec's planted positives are seeded to fire |
| `WARN: rule 'law_firm_cash_structuring' is active but entity is accounting` | Wrong entity-type rules left active | Set `status: inactive` on rules that don't apply to your DNFBP type |

---

## Next steps

- [How to verify the audit chain](verify-audit-chain.md) — the hash-chain guarantee that makes the manifest attestation meaningful.
- [How to export per-case / per-batch evidence packs](export-case-pack.md) — hand AUSTRAC a case-scoped ZIP, not the entire run.
- [Triage defects from `defect_log.jsonl`](triage-defects.md) — the quality lens for rule-level issues your first run surfaces.
- [`jurisdictions.md`](../jurisdictions.md) — the AU section, with AUSTRAC Tranche 2 scope detail and the `au_dnfbp` spec reference.
- **Sources:** [AUSTRAC Tranche 2 regulatory expectations 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26) · [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform) · [AUSTRAC: How to comply](https://www.austrac.gov.au/business/how-comply-guidance-and-resources)
