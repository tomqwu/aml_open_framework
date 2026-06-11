# How to plan AML program implementation after the Effectiveness NPRM + GENIUS Act comment windows closed

> **When you need this:** The FinCEN Effectiveness NPRM (FR 2026-07033) and GENIUS Act PPSI NPRM (FR 2026-06963) comment windows **closed June 9, 2026**. The rulemakings are pending — no final rule has been published. Once finalised (expected late 2026 / early 2027), firms have **12 months to implement**. This guide helps you complete a gap analysis now, before the implementation clock starts.
>
> **Prereqs:** `aml-open-framework` installed; a working spec (`aml validate` passes). For PPSI-specific steps: the `genius_ppsi_stablecoin` example spec (`examples/genius_ppsi_stablecoin/aml.yaml`).
>
> **Time:** ~30–60 min for a gap analysis against a working spec.

---

!!! info "The 12-month clock hasn't started yet"
    A gap analysis done **now** (June 2026) is a head start. The implementation clock starts at the *final rule* — expected late 2026 or early 2027. Firms that completed gap analyses during the comment period have documented evidence of proactive compliance posture. Firms that deferred are not out of time — but the window narrows once the final rule publishes.

---

## Part 1 — Effectiveness NPRM implementation checklist

The Effectiveness NPRM proposes reframing the BSA program rule around an **"effective, risk-based, reasonably designed"** standard. The four pillars of the proposed standard map directly to framework capabilities.

### Pillar 1 — Enterprise-wide risk assessment (program *established*)

The NPRM requires a documented enterprise-wide risk assessment as a **pillar**, not just expected practice.

**Gap check:**

```bash
# Does your spec link every active rule to a regulation reference?
aml validate --strict examples/canadian_schedule_i_bank/aml.yaml
```

A `--strict` pass means every active rule has:
- `regulation_refs` — tracing the rule back to the regulatory risk that drives it
- `risk_tier` — low/medium/high — your documented assessment of where the rule sits in your risk profile
- `typology` — the financial-crime typology the rule targets

If `aml validate --strict` emits warnings about missing `regulation_refs` or `risk_tier` on active rules, those are your gap items.

**Fix each gap:**

```yaml
rules:
  - id: large_cash_structuring
    risk_tier: high
    regulation_refs:
      - FinCEN 31 CFR 1020.315 (structuring)
      - AMLA 2020 s.6101 (national priorities)
    typology: cash_structuring
```

### Pillar 2 — Program maintenance evidence (*program maintained*)

The NPRM distinguishes "technical failure" (program established but a control slipped) from "systemic failure" (program never adequately established). The `decisions.jsonl` ledger is the evidence that a program is **maintained** — it shows that controls ran, alerts fired, and decisions were documented on each run.

```bash
# Verify your ledger is intact and hash-chained
aml verify-decisions runs/<run-dir>/
# Expected: "Ledger integrity: PASS — N decisions, chain intact"
```

The `AuditLedger.verify_decisions()` output is the maintenance evidence. Run it after each production run and keep the pass/fail in your board reports.

### Pillar 3 — Independent testing

The NPRM requires independent testing of the AML program. The equivalence report is the closest available framework artifact:

```bash
# If you have a prior run from a different spec version:
aml equivalence <old-run-dir> <new-run-dir> --markdown
```

If you use the champion-challenger validation flow (M3):

```bash
aml run <spec> --labels labels.csv --challenger-weights challenger.json
# Produces priority_outcome.json — precision@k / recall comparison
```

The `priority_outcome.json` documents that your current configuration was tested against an alternative, with a documented winner. This is the SR 26-2 independent-challenger artifact the NPRM is now proposing to extend program-wide.

### Pillar 4 — FinCEN national priorities incorporation

The NPRM requires programs to incorporate FinCEN national priorities (updated periodically — most recently 2024). Check your `regulation_refs`:

```bash
# Search your spec for national-priorities citations
grep -r "national_priorities\|FinCEN NP\|2024-01\|2020-01" examples/*/aml.yaml
```

At minimum, your highest-severity rules targeting elder fraud, human trafficking, cyber crime, and virtual currency should carry a FinCEN national priority citation. Add them if missing:

```yaml
regulation_refs:
  - FinCEN National Priorities 2024 — Cyber-enabled financial crime
```

### Whistleblower NPRM readiness (same June 9 close)

The FinCEN Whistleblower Incentives and Protections NPRM (FR 2026-06271) also closed June 9. Run the readiness table:

```bash
aml whistleblower-audit examples/canadian_schedule_i_bank/aml.yaml runs/<run-dir>/ \
  --format nprm-gap
```

The `--format nprm-gap` output produces a ✓/⚠/✗ readiness table against the NPRM's proposed expectations (SAR backlog exposure, escalation coverage, triage time, board-documented decisions, ledger integrity). Any ⚠ or ✗ rows are implementation items.

---

## Part 2 — GENIUS Act PPSI implementation checklist (stablecoin issuers)

The GENIUS Act PPSI NPRM proposes treating permitted payment stablecoin issuers (PPSIs) as financial institutions under the BSA, and imposing mandatory OFAC sanctions programs under new **31 CFR Part 502**.

### BSA program equivalence assessment

Start from the richer NPRM-grounded spec:

```bash
aml validate examples/genius_ppsi_stablecoin/aml.yaml
aml run examples/genius_ppsi_stablecoin/aml.yaml --seed 42
```

The `genius_ppsi_stablecoin` spec covers:
- Six stablecoin typologies (mint/burn/redeem velocity, nested-VASP layering, sanctioned-wallet, rapid-redemption, large-value concentration, cross-chain obfuscation)
- SAR + proposed PPSI CTR filing (`report_type: SAR`, `ctr_type: CTR_PPSI`)
- Filing-latency SLA for the proposed 31 CFR 1033.310 currency-transaction report
- OFAC 31 CFR Part 502 sanctions-program citations on every sanctions-related rule

### OFAC 31 CFR Part 502 sanctions program gaps

The NPRM proposes a dedicated OFAC sanctions compliance program for PPSIs — separate from the BSA AML program. Check your spec's sanctions-screening rules:

```bash
grep -A5 "sanctions\|ofac\|sdn\|blocked_wallet" examples/genius_ppsi_stablecoin/aml.yaml
```

Every sanctions-screening rule should carry:
```yaml
regulation_refs:
  - OFAC 31 CFR Part 502 (proposed — GENIUS Act PPSI NPRM)
  - OFAC SDN List
```

### ISO 20022 data contracts

Stablecoin transaction flows use ISO 20022 pacs.008/009/004 formats natively. Verify your data contract includes the ISO 20022 fields the proposed rule requires:

```bash
aml validate-data examples/genius_ppsi_stablecoin/aml.yaml data/input/
```

The `data/iso20022/parser.py` module handles pacs.008/009/004 + pain.001. If your transactions arrive as JSON (common for stablecoin rails), map them to the ISO 20022 fields before running the engine.

---

## Part 3 — Using the framework's gap-analysis artifacts

### Produce a machine-readable gap list

```bash
# Full strict validation — gap items are WARN/ERROR in output
aml validate --strict <your-spec.yaml> 2>&1 | grep -E "WARN|ERROR"
```

Save this output as your **implementation gap register**. Each line is a control gap with a machine-verifiable fix path.

### AMLA RTS effectiveness pack (EU banks only)

If you operate under EU supervision and are simultaneously managing AMLA RTS implementation (July 10 submission deadline), produce the AMLA effectiveness report to cross-reference your EU gaps:

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml runs/<run-dir>/ --markdown
```

The report produces a citation-coverage table (✓ mapped / ∼ partial / ✗ gap) for the three AMLR articles (Art. 28(1) CDD, Art. 26 ongoing monitoring, Art. 20(1)(d) sanctions screening). Gaps in this table are also implementation items under the AMLR 2027 application date.

### Export a board-ready gap artifact

```bash
aml export runs/<run-dir>/ --out implementation_gap_pack.zip
```

The `implementation_gap_pack.zip` contains the spec hash (your current program version), the `decisions.jsonl` ledger, and all per-run artifacts. This is the artifact you present to your board when requesting approval for the implementation roadmap.

---

## Verify it worked

```bash
# 1 — All active rules have regulation_refs and risk_tier
aml validate --strict <your-spec.yaml>
# No WARN on regulation_refs or risk_tier = gap items addressed

# 2 — Ledger integrity passes
aml verify-decisions runs/<latest-run-dir>/

# 3 — Whistleblower readiness table shows no ✗ rows
aml whistleblower-audit <spec> runs/<latest-run-dir>/ --format nprm-gap
```

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `--strict` warns "missing regulation_refs" | Rules not yet linked to NPRM citations | Add `regulation_refs` to each active rule |
| `aml amla-effectiveness-report` not found | Framework version pre-v0.1.47 | `pip install --upgrade aml-open-framework` |
| `priority_outcome.json` not produced | `--labels` flag requires a labelled alert set | Create a minimal `labels.csv` with known positives from historical cases |
| `whistleblower-audit` exits non-zero | `manifest.json` missing `as_of` field | Re-run `aml run` to generate a fresh manifest |

---

## Implementation timeline

| Milestone | Target | Framework artifact |
|---|---|---|
| Gap analysis complete | Now (June 2026) | `aml validate --strict` output |
| Board briefing on gap register | Q3 2026 | `implementation_gap_pack.zip` |
| Final rule published | Late 2026 / early 2027 | — |
| 12-month clock starts | At final rule | — |
| Program updated and re-validated | Final rule + 10 months | `aml validate --strict` clean pass |
| Board re-approval of updated program | Final rule + 11 months | Updated `manifest.json` hash + board minutes |
| Implementation deadline | Final rule + 12 months | `aml run` in prod + `decisions.jsonl` active |

---

## Next steps

- **[Stand up a GENIUS Act PPSI program](genius-ppsi-compliance.md)** — full PPSI spec walkthrough
- **[Run a FinCEN Whistleblower audit](run-whistleblower-audit.md)** — NPRM readiness table
- **[Produce an AMLA RTS effectiveness pack](produce-amla-effectiveness-pack.md)** — for EU-supervised banks
- **[Promote a rule across environments](promote-rule.md)** — dev → test → prod sign-off flow
- **[AUSTRAC Tranche 2 go-live readiness](austrac-tranche2-readiness.md)** — if you also operate in Australia

---

*Sources: [Federal Register 2026-07033 — Effectiveness NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs) · [Federal Register 2026-06963 — GENIUS Act PPSI NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism) · [Federal Register 2026-06271 — FinCEN Whistleblower NPRM](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections) · [FRB SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)*
