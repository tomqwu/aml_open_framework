# How to generate an AMLA RTS effectiveness report

> **When you need this:** Your EU AML program needs to demonstrate effectiveness against AMLA's three regulatory technical standards (CDD information — AMLR Art. 28(1); ongoing monitoring of business relationships — AMLR Art. 26; targeted-financial-sanctions screening — AMLR Art. 20(1)(d)). The `aml amla-effectiveness-report` CLI (#528) rolls your run into an alert→case→STR funnel, computes per-rule precision/recall, and produces a RTS-citation-coverage map — a frozen, regulator-facing artifact you can hand to an EU supervisor or 2LoD reviewer.
>
> **Prereqs:** A completed run directory (`aml run aml.yaml --seed 42` produces one). Your spec must have at least one rule carrying one of the three AMLR effectiveness citations — the `eu_bank` example spec (`examples/eu_bank/aml.yaml`) ships with all three. The CLI is offline and post-run — it never blocks or changes the run.
>
> **Time:** ~5 min.

The AMLA effectiveness report is **advisory and derived**. It reuses the same alert→case→STR funnel as `metrics.outcomes.compute_outcomes` — no new counting logic — and adds a per-RTS coverage map: which rules carry the three AMLR citations that AMLA's effectiveness RTS require, whether they have supporting evidence, and which are gaps. STR *acceptance* is reported `not_tracked` (it is a regulator-feedback event the run cannot record); per-rule *recall* stays `None` (it requires the ground-truth positive population). Nothing is fabricated.

---

## Steps

### 1 · Complete a run

```bash
aml run examples/eu_bank/aml.yaml --seed 42
```

This produces a run directory (e.g. `.artifacts/run-2026-06-19T.../`). The report reads `manifest.json`, `decisions.jsonl`, and the `cases/` directory from this run.

### 2 · Generate the report

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml .artifacts/run-*/
```

The CLI emits a frozen `amla_effectiveness_report.json` in the run directory and prints a summary to stdout. The report is pinned in `manifest.json` by SHA-256 hash.

For a markdown table suitable for model-risk committee reports or board packs:

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml .artifacts/run-*/ --markdown
```

### 3 · Read `amla_effectiveness_report.json`

```bash
jq . .artifacts/run-*/amla_effectiveness_report.json
```

Key sections:

```json
{
  "generated_at": "2026-06-19T00:00:00+00:00",
  "funnel": {
    "total_alerts": 42,
    "total_cases": 28,
    "total_strs": 6,
    "str_acceptance": "not_tracked"
  },
  "rule_precision": [
    {
      "rule_id": "correspondent_sanctions_exposure",
      "alerts": 9,
      "cases": 7,
      "strs": 2,
      "precision": 0.286,
      "recall": null
    }
  ],
  "rts_coverage": [
    {
      "citation": "AMLR Art. 28(1)",
      "rts": "CDD information RTS",
      "status": "mapped",
      "rules": ["enhanced_cdd_high_risk_country", "beneficial_owner_verification"]
    },
    {
      "citation": "AMLR Art. 26",
      "rts": "Ongoing monitoring of business relationships",
      "status": "partial",
      "rules": ["transaction_volume_spike"]
    },
    {
      "citation": "AMLR Art. 20(1)(d)",
      "rts": "Targeted-financial-sanctions screening",
      "status": "mapped",
      "rules": ["correspondent_sanctions_exposure"]
    }
  ]
}
```

### 4 · Interpret RTS coverage status

| `status` | Meaning | Action |
|---|---|---|
| `mapped` | At least one rule cites the AMLR article AND the run produced alert evidence | Coverage is evidenced — include in supervisor submission |
| `partial` | Rule cites the article but no alert evidence in this run (run may have been clean) | Check data volume; note in the supervisor packet that the control is deployed even if no alerts fired |
| `gap` | No rule in the spec cites this AMLR article | A control coverage gap — add a rule or cite an existing one |

### 5 · Read it on the dashboard instead

- **Framework Alignment (page 8)** — when the spec is an EU jurisdiction, a dedicated "AMLA RTS coverage" tab appears next to the other framework-alignment views. Each RTS row shows `✓ mapped / ∼ partial / ✗ gap` with a click-through to the rule evidence. The tab is rendered by `dashboard/frameworks.py::build_amla_rts_alignment` — no Streamlit import at module level.

---

## Adding AMLR citations to your rules

For the RTS coverage map to show `mapped` rather than `gap`, each rule must carry the AMLR article reference in its `regulation_refs` list. The citation format the matcher requires includes `AMLR` and the article:

```yaml
rules:
  - id: enhanced_cdd_high_risk_country
    regulation_refs:
      - "AMLR Art. 28(1) — CDD information RTS"
      - "AMLR Art. 26 — Ongoing monitoring (CDD measure Art. 20(1)(f))"
    # ...
```

A bare article number like `"Art. 28(1)"` without AMLR context will NOT match — the matcher requires the regulation context to avoid ambiguity with AMLD6 or other frameworks.

---

## Verify it worked

Three checks:

1. **`amla_effectiveness_report.json` exists** in the run dir and `manifest.json::amla_effectiveness_report_hash` matches `sha256(amla_effectiveness_report.json)`.
2. **`generated_at` equals the run's `as_of`** (not a wall-clock read). Same spec + same data + same seed → identical report.
3. **`str_acceptance` is `not_tracked`** — if it shows a number, the report is fabricating data the run doesn't record (a bug, not a feature).

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| All three RTS show `gap` | Rules don't carry AMLR citations | Add `regulation_refs` entries with `AMLR Art.` prefix to your rules |
| `str_acceptance` is a number | Bug — the report should never infer STR acceptance | File a bug; the run doesn't record regulator-feedback events |
| Report missing from run dir | Run was completed before `amla-effectiveness-report` was added | Re-run and re-generate; the CLI is offline and doesn't modify the existing run |
| `"AMLA Art. 19(9)"` doesn't match | Old citation — the correct AMLR articles are 28(1), 26, and 20(1)(d) | Update `regulation_refs` to the correct AMLR form |

---

## Next steps

- [`spec-reference.md`](../spec-reference.md) — `rule.regulation_refs` field-by-field.
- [`docs/jurisdictions.md`](../jurisdictions.md) — EU bank section: which rules in `eu_bank/aml.yaml` carry which AMLR citations.
- [How to monitor model risk](monitor-model-risk.md) — the sibling governance report. AMLA effectiveness covers RTS citation coverage; model-risk monitoring covers per-rule drift and validation cadence.
- [How to export per-case evidence](export-case-pack.md) — the evidence bundle the supervisor receives alongside the effectiveness report.
