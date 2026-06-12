# How to plan for post-NPRM implementation (Effectiveness + GENIUS Act)

> **When you need this:** The FinCEN Effectiveness NPRM (FR 2026-07033) and the GENIUS Act PPSI NPRM (FR 2026-06963) comment windows both **closed 2026-06-09** — the rulemakings are pending. Expected final rules: late 2026 / early 2027. Once finalised, firms have **12 months** to implement. This recipe is the compliance planning guide for the implementation window that starts at the final rule.
>
> **Prereqs:** A working `aml validate` + `aml run` install. For the PPSI path: `examples/genius_ppsi_stablecoin/aml.yaml`. For the Effectiveness NPRM path: any US-jurisdiction spec. For the whistleblower-readiness table: a completed `aml run` directory.
>
> **Time:** ~20 min for a first gap analysis pass.

A gap analysis done now — 8–10 months before the expected final rule — is the compliance posture that distinguishes "proactive" from "reactive" when examiners arrive. The framework already produces machine-readable gap artifacts from `aml validate --strict` and `aml whistleblower-audit --format nprm-gap`. This recipe walks how to use both to build your 12-month implementation evidence trail.

---

## Part 1 — Effectiveness NPRM implementation checklist

The Effectiveness NPRM frames a BSA program around an **"effective, risk-based, reasonably designed"** standard. Its two pillars map onto framework artifacts:

| NPRM pillar | Framework evidence | CLI / field |
|---|---|---|
| Program **established** — formal, documented | `aml validate --strict` clean pass + `manifest.json` hash | `aml validate examples/us_community_bank/aml.yaml --strict` |
| Program **maintained** — actively run and monitored | `decisions.jsonl` hash chain (ongoing engine runs) | `aml verify-decisions .artifacts/run-<ts>` |
| Enterprise-wide risk assessment documented | All active rules have `risk_tier` + `regulation_refs` citations | `aml validate --strict` warns on missing `risk_tier` |
| National priorities incorporated | `regulation_refs` on active rules traces to FinCEN national priorities | Rule-level `regulation_refs` in your spec |

### Step 1 · Run strict validation

```bash
aml validate examples/us_community_bank/aml.yaml --strict
```

Every `WARN` or `ERROR` is a gap the final rule will likely require you to close. Address them now while the 12-month clock hasn't started.

### Step 2 · Run the whistleblower NPRM readiness gap

The FinCEN Whistleblower Incentives and Protections NPRM (FR 2026-06271, comment window closed 2026-06-01) runs on the same implementation timeline as the Effectiveness NPRM. Both share a final-rule window of late 2026 / early 2027.

```bash
aml run examples/us_community_bank/aml.yaml --seed 42
aml whistleblower-audit examples/us_community_bank/aml.yaml .artifacts/run-<ts> \
  --format nprm-gap
```

The gap table maps each NPRM-proposed expectation to ✓ / ⚠ / ✗:

```
| Proposed requirement             | Status | Evidence                           |
| Internal reporting channel documented | ✓  | ledger_integrity=verified          |
| Median triage < 30d              | ✓      | triage_time.median_days=1.1        |
| SAR backlog ≤ 0                  | ✓      | sar_backlog_exposure=0             |
| Board-level escalation documented | ⚠      | board_documented_decisions=not tracked |
```

A `⚠` row means the signal isn't being tracked yet — not that there's a gap. Wire board-report events into the audit ledger and the row resolves to ✓ once your board reporting is connected.

### Step 3 · Export a gap-analysis bundle

```bash
aml export .artifacts/run-<ts> --out effectiveness_nprm_gap_pack.zip
```

The ZIP carries the manifest, decisions ledger, and the audit artifacts. This is your documented evidence of proactive compliance posture. Run it monthly between now and the final rule — each run's manifest hash is a timestamped snapshot of your program's state.

---

## Part 2 — GENIUS Act PPSI implementation checklist (stablecoin issuers)

For banks sponsoring PPSIs and stablecoin issuers, the GENIUS Act PPSI NPRM proposes treating PPSIs as financial institutions under the BSA and adding a mandatory OFAC sanctions program under 31 CFR Part 502. The `examples/genius_ppsi_stablecoin/aml.yaml` spec is the NPRM-grounded template.

### Step 1 · Validate the PPSI stablecoin spec

```bash
aml validate examples/genius_ppsi_stablecoin/aml.yaml --strict
```

### Step 2 · Assess your BSA-program equivalence

The NPRM's key additions vs the existing MSB rules (31 CFR 1022):

| NPRM requirement | Framework mapping | Spec field to verify |
|---|---|---|
| BSA program (AML/CFT policies + procedures) | All active rules with `regulation_refs` citing GENIUS Act s.4 | `rule.regulation_refs` |
| OFAC sanctions program (31 CFR Part 502) | Sanctions screening rule (list_match on SDN list) | `rule.id: ofac_sanctions_screening` |
| ISO 20022 pacs.008 / pacs.009 / pacs.004 fields | `txn` data contract with `debtor_bic`, `creditor_bic`, `uetr` | `data_contract.schema` |
| SAR + proposed PPSI CTR (31 CFR 1033.310) | `report_type: FINCEN_SAR` + `FINCEN_CTR` in `reporting.forms` | `reporting.forms` |
| Filing-latency SLA | `program.sla` block with SAR/CTR filing windows | `program.sla` |

### Step 3 · Run against the PPSI stablecoin spec

```bash
aml run examples/genius_ppsi_stablecoin/aml.yaml --seed 42
```

Confirm every planted typology fires: stablecoin mixing/layering, rapid on-ramp/off-ramp cycling, structuring below $10k, VASP counterparty exposure, OFAC SDN screening, adverse media.

### Step 4 · Generate the gap-analysis artifact

```bash
aml validate examples/genius_ppsi_stablecoin/aml.yaml --strict
aml export .artifacts/run-<ts> --out ppsi_nprm_gap_pack.zip
```

---

## Part 3 — Using the framework as ongoing evidence

The 12-month implementation clock starts at the **final** rule. Use the intervening period to build a dated evidence trail:

1. **Monthly runs** — `aml run` each month against your live data. Each `manifest.json` hash is a tamper-evident snapshot.
2. **Strict validation** — run `aml validate --strict` after every spec change. The warning/error list is your living gap register.
3. **Whistleblower audit** — run `aml whistleblower-audit --format nprm-gap` monthly so the board can see readiness trending toward ✓ across all proposed requirements.
4. **Export the bundle** — `aml export` each monthly run and retain the ZIPs. When examiners ask "show me your gap analysis trail," you have timestamped, hash-chained artifacts from 8 months before the final rule.

---

## Verify it worked

1. `aml validate --strict` passes with zero ERRORs (WARNs are noted and tracked).
2. The whistleblower audit NPRM gap table has no ✗ rows.
3. A dated `manifest.json` exists for each monthly run — the manifest hashes form your audit trail.
4. The PPSI spec (if applicable) fires all six stablecoin typologies at `--seed 42`.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `strict` fails on `risk_tier` | Active rule missing `risk_tier` | Add `risk_tier: low / medium / high` to every active rule |
| Whistleblower `escalation_coverage_pct` stays at 0% | Dispositions are engine-simulated (no human reviewer metadata) | Expected on synthetic runs; coverage rises when analysts disposition cases through the dashboard |
| PPSI OFAC rule not firing | SDN watchlist not populated in test data | The planted `genius_ppsi_stablecoin` synthetic data includes a sanctioned-wallet transaction at seed 42 |
| `manifest.json` missing `as_of` | Run didn't complete successfully | Check `aml run` exit code; a non-zero exit means the run failed before finalizing |

---

## Next steps

- [How to run a FinCEN Whistleblower internal-channel audit](run-whistleblower-audit.md) — the NPRM readiness tool used in Part 1.
- [How to stand up a GENIUS Act PPSI program](genius-ppsi-compliance.md) — the full PPSI spec walkthrough.
- [How to verify the audit chain](verify-audit-chain.md) — the hash-chain integrity check that validates your monthly evidence trail.
- **Sources:** [FR 2026-07033 — Effectiveness NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs) · [FR 2026-06963 — GENIUS Act PPSI NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism) · [FR 2026-06271 — Whistleblower NPRM](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
