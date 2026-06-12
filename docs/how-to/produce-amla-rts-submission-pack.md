# How to prepare an AMLA RTS submission pack

> **When you need this:** AMLA's statutory deadline to submit final RTS to the European Commission is **2026-07-10 — 28 days away** (as of 2026-06-12). You are an EU-supervised obliged entity (credit institution, payment institution, EMI, or large VASP) operating in 1+ EU member states, and you need to close your alignment gaps against the three AMLR effectiveness articles before the standard locks in. After July 10, the RTS framework is submitted and any remaining gaps become implementation backlogs against the **July 2027 application date** (AMLR Art. 1 first application date). This recipe walks the pre-submission readiness checklist.
>
> **Prereqs:** A spec with `jurisdiction: EU` (or a multi-jurisdiction spec with EU rules). The bundled `examples/eu_bank/aml.yaml` is the demonstrator. One completed `aml run`. The `aml amla-effectiveness-report` CLI (#528).
>
> **Time:** ~15 min to produce the pack; citation-gap closure depends on your rule count.

The submission pack is your documented evidence that your program is *aligned* before the standard locks. It does not go to AMLA directly — AMLA is submitting the RTS text to the Commission; you are closing your internal gaps against what that text will require. The `amla_effectiveness_report.json` artifact produced here is your alignment record.

---

## Steps

### Step 1 · Confirm EU supervision scope

Entities in scope for AMLA direct supervision (2027 onward) and AMLR obligations:

- Credit institutions (`CRD` licensed) in any EU member state
- Payment institutions and EMIs (`PSD2` licensed)
- VASPs registered with a national competent authority (NCA)
- AML obliged entities under AMLD6 (Directive (EU) 2024/1640)

If your spec covers an EU-supervised entity, it should carry `regulation_refs` on active rules linking to AMLR (Regulation (EU) 2024/1624) articles.

### Step 2 · Annotate rules with the three AMLR effectiveness citations

The three AMLR effectiveness obligations the `aml amla-effectiveness-report` CLI checks:

| Obligation | AMLR citation | What it covers |
|---|---|---|
| CDD information RTS | `AMLR Art. 28(1)` | Customer-due-diligence measures — CDD information the obliged entity must collect |
| Ongoing monitoring of the business relationship | `AMLR Art. 26` (CDD measure `Art. 20(1)(f)`) | Continuous monitoring controls — ongoing CDD |
| Targeted-financial-sanctions screening | `AMLR Art. 20(1)(d)` | Screening against EU/UN/OFAC sanctions lists |

Each rule that reflects one of these obligations should carry the matching citation:

```yaml
rules:
  - id: cdd_high_risk_customer
    regulation_refs:
      - citation: "AMLR Art. 28(1)"
        description: "CDD information RTS — customer-risk profiling satisfies Art. 28(1) information requirements."

  - id: dormant_account_reactivation
    regulation_refs:
      - citation: "AMLR Art. 26"
        description: "Ongoing monitoring of the business relationship (CDD measure Art. 20(1)(f))."

  - id: eu_sanctions_screening
    regulation_refs:
      - citation: "AMLR Art. 20(1)(d)"
        description: "Targeted-financial-sanctions screening (EU/UN/OFAC consolidated list)."
```

### Step 3 · Validate the spec

```bash
aml validate examples/eu_bank/aml.yaml --strict
```

A clean strict pass confirms every active rule has a `risk_tier` and all cross-references are intact. Fix any ERRORs before producing the effectiveness pack — the pack derives its coverage from the validated spec.

### Step 4 · Run the engine

```bash
aml run examples/eu_bank/aml.yaml --seed 42
```

### Step 5 · Produce the AMLA effectiveness pack

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml .artifacts/run-<ts> \
  --markdown amla_rts_submission_pack.md
```

This writes two artifacts:
- `amla_effectiveness_report.json` — the frozen, manifest-pinned effectiveness record.
- `amla_rts_submission_pack.md` — a pipe table for your MRC / regulatory-submissions team.

Console summary:

```
AMLA RTS effectiveness eu_bank_aml
  alerts: 89  cases: 89  str_filed: 83
  alert→str: 93.26%  str_acceptance: not_tracked
  RTS coverage: 3/3 articles
```

`str_acceptance: not_tracked` is correct and expected — the run records STR *filing* (`escalated_to_str`) but not regulator *acceptance*. That is a FIU-feedback loop that lives outside the framework; reporting it as `not_tracked` is honest and satisfies the AMLA reporting standard (the AMLA RTS covers program effectiveness, not post-filing regulator feedback).

### Step 6 · Interpret the RTS coverage table

From the `--markdown` output:

```
| AMLR Article | Obligation | Covering rules | Status |
|---|---|---|---|
| Art. 28(1) | CDD information RTS | high_risk_jurisdiction, structuring_cash | ✓ covered |
| Art. 26    | Ongoing monitoring of the business relationship | dormant_account_reactivation, pep_enhanced_dd | ✓ covered |
| Art. 20(1)(d) | Targeted-financial-sanctions screening | eu_sanctions_screening | ✓ covered |
```

- **✓ covered** — ≥1 active rule cites the article. You have documented evidence.
- **∼ partial** — rule cites the article but produced no alerts (no evidence trail). Consider whether the rule threshold is calibrated.
- **✗ gap** — no active rule cites the article. This is an alignment gap to close before July 10.

### Step 7 · Close citation gaps

For each ✗ row:
1. Identify which rule(s) implement the obligation.
2. Add the `regulation_refs` citation to that rule.
3. Re-run `aml validate` to confirm the spec is still valid.
4. Re-run `aml amla-effectiveness-report` — the row should move from ✗ to ✓.

### Step 8 · Export the submission pack

```bash
aml export .artifacts/run-<ts> --out amla_rts_pack.zip
```

The ZIP carries the manifest (with SHA-256 hash), `decisions.jsonl`, `amla_effectiveness_report.json`, and all case packs. This is your pre-submission evidence bundle.

---

## Verify it worked

1. `aml validate --strict` exits clean.
2. `amla_effectiveness_report.json` has `n_rts_covered: 3` — all three AMLR articles covered.
3. No ✗ rows in the `--markdown` coverage table.
4. `str_acceptance_status` is `not_tracked` — not fabricated.
5. Re-running the effectiveness report against the same run directory produces byte-identical output (determinism check).

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `RTS coverage: 0/3 articles` | No rule carries an AMLR Art. 28(1) / Art. 26 / Art. 20(1)(d) citation | Add the citations following Step 2 |
| `✗ gap` for Art. 26 | No rule monitors the ongoing business relationship | The bundled `eu_bank` spec has `dormant_account_reactivation` for this; add a comparable rule |
| `str_acceptance_status` shows a percentage | Your spec fabricated this field | This is a bug — the framework should report `not_tracked`; open an issue |
| `WARN: active rule <id> missing risk_tier` | Rule lacks `risk_tier` | Add `risk_tier: low / medium / high`; required for `--strict` pass |
| Dashboard shows no AMLA RTS coverage tab | Spec `jurisdiction` is not EU | The tab is EU-only; ensure `program.jurisdiction: EU` |

---

## Next steps

- [How to produce an AMLA RTS effectiveness pack](produce-amla-effectiveness-pack.md) — the deeper dive on the `aml amla-effectiveness-report` CLI: per-rule precision, JSON shape, and dashboard integration (Framework Alignment page 8).
- [How to monitor model risk + per-rule drift](monitor-model-risk.md) — the sibling SR 11-7 / OSFI E-23 compliance pack.
- [`jurisdictions.md`](../jurisdictions.md) — the EU section, with AMLA direct-supervision selection exercise details.
- **Sources:** [AMLA CDD RTS consultation](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-customer-due-diligence_en) · [AMLA business-relationships RTS consultation](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-criteria-identifying-business-relationships-occasional-and-linked_en) · [AMLA pecuniary-sanctions RTS consultation](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-pecuniary-sanctions-administrative-measures-and-periodic-penalty-payments_en) · [AMLA selection exercise press release](https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en)
