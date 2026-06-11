# How to stand up an AUSTRAC Tranche 2 compliant AML/CTF program

> **When you need this:** You are an Australian lawyer, accountant, real-estate agent, or dealer in precious metals and stones (DPMS) — a "Tranche 2" DNFBP — and need a board-approved, AUSTRAC-compliant AML/CTF program operational by **July 1, 2026**.
>
> **Prereqs:** Python 3.10+ installed, `pip install aml-open-framework`; AUSTRAC online portal account for enrolment.
>
> **Time:** ~2–4 hours for a lean first program; ~1 day for a fully customised spec.

---

!!! warning "Enforcement begins July 1, 2026"
    AUSTRAC Tranche 2 is now law. From July 1, every in-scope DNFBP must be enrolled with AUSTRAC and have a **board-approved AML/CTF program** in place. AUSTRAC's stated first-cycle posture favours **enforceable undertakings (EUs)** over fines — but only for firms with documented good-faith compliance efforts. A board-approved program, even a lean one, is the difference between an EU and an immediate penalty on day one.

---

## Step 1 — Confirm your enrolment status

All Tranche 2 DNFBPs must be enrolled with AUSTRAC before providing designated services.

1. Navigate to [AUSTRAC Online](https://online.austrac.gov.au) and sign in (or create an account).
2. Click **Enrol** and select your business category:
   - **Legal practitioners** — providing conveyancing, trust/company management, or large-value asset transactions
   - **Accountants** — providing trust/company management or large-value asset transactions
   - **Real estate agents** — in sales and leases of real property
   - **Dealers in precious metals and stones (DPMS)**
3. Complete the enrolment form. The key fields the framework's spec maps to are:
   - `program.entity_name` → your legal entity name
   - `program.jurisdiction` = `AU`
   - `program.filing_authority` = `AUSTRAC`
4. AUSTRAC will issue you a **reporting entity ID**. Record this — you will need it for SMR and TTR submissions.

---

## Step 2 — Generate your AML/CTF program using the example spec

The framework ships a complete AU/AUSTRAC DNFBP example spec covering all four Tranche 2 entity types with SMR and TTR filing:

```bash
# Clone or inspect the example spec
cat examples/au_dnfbp/aml.yaml
```

### Customise the spec for your entity

At minimum, update these fields in `examples/au_dnfbp/aml.yaml`:

```yaml
program:
  name: "Your Entity Name AML/CTF Program"
  entity_name: "Your Legal Entity Pty Ltd"
  jurisdiction: AU
  filing_authority: AUSTRAC
  environment: prod
  report_type: SMR          # Australia files Suspicious Matter Reports (NOT STRs)
  ctr_type: TTR             # Threshold Transaction Reports at AUD 10,000

rules:
  # Remove rules that don't apply to your designated service category.
  # Every active rule must have risk_tier set (low/medium/high).
```

### Validate the spec

```bash
aml validate examples/au_dnfbp/aml.yaml
aml validate --strict examples/au_dnfbp/aml.yaml
```

A clean `--strict` pass means:
- Every active rule has a `risk_tier` and `regulation_refs`
- All data contracts are structurally sound
- Cross-references are consistent

The `aml validate` output **is** your machine-readable program specification — the first exhibit in a board attestation package.

---

## Step 3 — Run the engine and generate your Compliance Manifest

```bash
aml run examples/au_dnfbp/aml.yaml --seed 42
```

This produces a run directory (e.g. `runs/au_dnfbp__2026-07-01T000000/`) containing:

| Artifact | What it is | AUSTRAC relevance |
|---|---|---|
| `manifest.json` | Spec hash + run hash + timestamp | Board attestation anchor — "program was in this state at this date" |
| `decisions.jsonl` | Append-only SHA-256 hash-chained alert ledger | Ongoing monitoring evidence |
| `cases/*.json` | Per-alert case bundles | SMR filing artefacts |
| `audit_pack.zip` | Regulator-ready ZIP | Hand to AUSTRAC on request |

The `manifest.json` hash is your **board-approved program version**. Print it, present it to your board, and record the board's approval date alongside it. That is the documented good-faith compliance posture AUSTRAC looks for.

### What "board-approved" means in practice

AUSTRAC requires a board-approved AML/CTF program. The Compliance Manifest converts this from a narrative document into a versioned, hash-anchored artifact:

```bash
# The spec + manifest hash = the thing your board approves
cat runs/au_dnfbp__*/manifest.json | python3 -c "
import json, sys
m = json.load(sys.stdin)
print(f'Program version: {m[\"spec_hash\"][:16]}')
print(f'Run timestamp:   {m[\"as_of\"]}')
print(f'Rules active:    {m[\"rule_count\"]}')
"
```

Board minutes should reference the `spec_hash` (or the first 16 characters) as the program version the board reviewed and approved.

---

## Step 4 — Configure SMR filing readiness

Australia files **Suspicious Matter Reports (SMRs)**, not Suspicious Transaction Reports (STRs). The framework handles this via:

```yaml
program:
  report_type: SMR          # tells the engine to label outputs as SMRs, not STRs
```

### Generate an SMR bundle for a case

```bash
# Export a case bundle — includes goAML-compatible XML and narrative
aml export-case <case_id> --out smr_bundle/
```

The `cases/str_bundle.py` module (named for the general STR/SMR family) produces:
- `goAML_smr.xml` — AUSTRAC's goAML submission format
- `narrative.txt` — human-readable narrative for the SMR
- `manifest_hash` embedded in every artifact for chain-of-custody

### Threshold Transaction Reports (TTRs)

TTRs are required for cash transactions ≥ AUD 10,000. Configure:

```yaml
program:
  ctr_type: TTR
  ctr_threshold: 10000
  ctr_currency: AUD
```

The framework generates TTR artifacts alongside SMR artifacts on every run.

---

## Step 5 — Ongoing monitoring after July 1

AUSTRAC expects ongoing customer due diligence (CDD) and transaction monitoring as part of your program, not just enrolment.

### Schedule regular runs

```bash
# Add to cron or CI — daily or weekly depending on transaction volume
aml run examples/au_dnfbp/aml.yaml --seed 42
```

### What AUSTRAC's first-cycle inspection looks for

AUSTRAC inspectors under the first enforcement cycle (post-July 1) will look for:

| What they ask | Framework evidence |
|---|---|
| "Do you have a board-approved program?" | `manifest.json` spec hash + board minutes referencing the hash |
| "Is your program up to date?" | Most recent run timestamp vs programme change history |
| "Show us your CDD process" | Active rules with `regulation_refs: [AUSTRAC AML/CTF Act s.36]` |
| "How do you detect suspicious activity?" | Rule definitions in the spec + `decisions.jsonl` alert history |
| "Have you filed any SMRs?" | `cases/*/goAML_smr.xml` artifacts in the audit pack |
| "Can we see your audit trail?" | `aml export` → `audit_pack.zip` handed to the inspector |

### Export a full regulator-ready bundle

```bash
aml export runs/au_dnfbp__2026-07-01T000000/ --out austrac_audit_pack.zip
```

This single ZIP contains everything an AUSTRAC inspector needs to verify your program.

---

## Verify it worked

```bash
# 1 — Spec validates cleanly under strict mode
aml validate --strict examples/au_dnfbp/aml.yaml
# Expected: "Validation passed (strict)"

# 2 — Run completes and produces manifest
aml run examples/au_dnfbp/aml.yaml --seed 42
ls runs/ | tail -1   # should show au_dnfbp__<timestamp>/

# 3 — Audit pack is exportable
aml export runs/au_dnfbp__*/  --out test_austrac_pack.zip
ls -lh test_austrac_pack.zip  # should be non-zero
```

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `aml validate` fails with "missing risk_tier on active rule" | Rule missing `risk_tier: low/medium/high` | Add `risk_tier` to every active rule in the spec |
| `aml run` exits with `ContractViolation` | A required data-contract column is absent from your input data | Check `Data Quality` dashboard or run `aml validate-data <spec> <data-dir>` |
| `report_type: SMR` not recognised | Old framework version | `pip install --upgrade aml-open-framework` |
| goAML XML not in case bundle | `program.report_type` not set to `SMR` | Set `report_type: SMR` in program block |

---

## Next steps

- **[Verify the audit chain](verify-audit-chain.md)** — prove your `decisions.jsonl` hasn't been tampered with before handing it to AUSTRAC
- **[Configure SLA monitoring](configure-sla.md)** — set SMR filing-latency SLAs (AUSTRAC expects prompt filing)
- **[Export per-case evidence](export-case-pack.md)** — produce single-case SMR bundles for individual investigations
- **[Run a FinCEN Whistleblower audit](run-whistleblower-audit.md)** — the `--format nprm-gap` output doubles as a governance-readiness checklist for any jurisdiction
- **[Jurisdictions reference](../jurisdictions.md#australia--austrac)** — AUSTRAC Tranche 2 coverage overview

---

*Sources: [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform) · [AUSTRAC regulatory expectations 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26) · [AUSTRAC: How to comply](https://www.austrac.gov.au/business/how-comply-guidance-and-resources)*
