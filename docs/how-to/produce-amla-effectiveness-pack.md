# How to produce an AMLA RTS effectiveness pack

> **When you need this:** You are an EU-supervised obliged entity (a credit institution, payment institution, EMI, or VASP) and the EU AML Authority (AMLA) wants to see, for one engine run, that your transaction-monitoring program is *effective* — the alert→case→STR funnel — and that your detection rules *evidence* the three RTS effectiveness standards: the CDD RTS (AMLR Art. 28(1)), the business-relationships RTS (AMLR Art. 19(9)), and the pecuniary-sanctions RTS (AMLD6 Art. 53(10)). The offline `aml amla-effectiveness-report` command (#528) rolls all of that into one frozen, deterministic artifact for your Model Risk Committee (MRC) / supervisory pack.
>
> **Prereqs:** A spec whose EU rules carry the AMLA RTS citations in their `regulation_refs` (the bundled `examples/eu_bank/aml.yaml` is the demonstrator). One completed `aml run` so the run dir has `cases/`, `decisions.jsonl`, and `manifest.json`. `metrics/amla_effectiveness.py::build_amla_effectiveness_report` is the canonical, pure builder.
>
> **Time:** ~5 min.

The pack is **offline and advisory** — it is a post-run report like `aml model-inventory`, NEVER in the engine run path. It *derives* every number from the run's own artifacts: the funnel + per-rule counts come straight from `metrics.outcomes.compute_outcomes` (so the AMLA pack and the existing outcomes pack never diverge), and the RTS coverage comes from each rule's `regulation_refs`. Nothing is fabricated — the run records STR *filing* (`escalated_to_str`) but not regulator *acceptance*, so `str_acceptance` is reported as `not_tracked` rather than invented. It is deterministic: `generated_at` is the run manifest's `as_of`, not a wall-clock read, so the same run yields byte-identical output.

---

## Steps

### 1 · Annotate your EU rules with AMLA RTS citations

Each rule whose logic reflects an RTS effectiveness standard carries the matching citation in `regulation_refs` (these are the real AMLR / AMLD6 references — AMLR = Regulation (EU) 2024/1624; AMLD6 = Directive (EU) 2024/1640):

```yaml
rules:
  - id: structuring_cash
    regulation_refs:
      - citation: "AMLR Art. 28(1)"        # CDD RTS
        description: "CDD RTS — customer-due-diligence measures the rule reflects."
  - id: pep_screening
    regulation_refs:
      - citation: "AMLR Art. 19(9)"        # business-relationships RTS
        description: "Ongoing monitoring of the PEP business relationship."
  - id: sanctions_screening
    regulation_refs:
      - citation: "AMLD6 Art. 53(10)"      # pecuniary-sanctions RTS
        description: "Targeted-financial-sanctions screening obligation."
```

The report maps a rule onto an RTS article when one of the rule's citations contains the article's reference (`AMLR Art. 28(1)`, `AMLR Art. 19(9)`, `AMLD6 Art. 53(10)`). A rule with no AMLA citation simply isn't counted toward coverage — it still appears in the per-rule funnel.

### 2 · Validate + run

```bash
aml validate examples/eu_bank/aml.yaml
aml run examples/eu_bank/aml.yaml --seed 42
```

### 3 · Produce the pack

```bash
aml amla-effectiveness-report examples/eu_bank/aml.yaml .artifacts/run-<TS> \
  --markdown amla_effectiveness.md
```

The command writes `amla_effectiveness_report.json` into the run dir (atomic write — a temp file in the same directory then `os.replace`, so an I/O error never leaves a partial artifact), an optional `--markdown` MRC table, and prints a summary:

```
AMLA RTS effectiveness eu_bank_aml
  alerts: 89  cases: 89  str_filed: 83
  alert→str: 93.26%  str_acceptance: not_tracked
  RTS coverage: 3/3 articles
```

Use `--out <path>` to write the JSON somewhere other than the run dir.

### 4 · Read the report

```bash
jq . .artifacts/run-<TS>/amla_effectiveness_report.json
```

```json
{
  "spec_program": "eu_bank_aml",
  "generated_at": "2026-06-09T18:31:51.015515",
  "total_alerts": 89,
  "total_str_filed": 83,
  "alert_to_str_pct": 93.26,
  "str_acceptance_rate_pct": null,
  "str_acceptance_status": "not_tracked",
  "rts_coverage": [
    {
      "key": "cdd",
      "title": "Customer due diligence",
      "citation": "AMLR Art. 28(1)",
      "instrument": "AMLR",
      "covering_rule_ids": ["high_risk_jurisdiction", "structuring_cash"],
      "status": "covered"
    }
  ],
  "n_rts_covered": 3
}
```

| Field | Meaning |
|---|---|
| `total_alerts` / `total_cases` / `total_str_filed` | The AMLA effectiveness funnel, derived from `cases/` + `decisions.jsonl`. |
| `alert_to_str_pct` | Overall conversion — the canonical AMLA effectiveness ratio. |
| `str_acceptance_status` | `not_tracked` — the run records STR *filing*, not regulator *acceptance*. Wire your FIU-feedback loop separately if you need this. |
| `rts_coverage[].status` | `covered` (≥1 rule cites the article) or `gap` (none). |
| `rules[].precision` | Per-rule precision — `null` unless you supply case labels (precision needs ground-truth labels the run doesn't carry). `recall` is always `null`; it needs the ground-truth positive population, which the alert set alone can't tell you. |

### 5 · Read it on the dashboard instead

- **Framework Alignment (page 8)** — for an EU program, an **"AMLA RTS coverage"** tab maps the spec's rule citations onto the three RTS articles with a ✓ (mapped) / ∼ (partial — cited but no evidence trail) / ✗ (gap) indicator and the covering rule ids. The mapping logic (`dashboard/frameworks.py::build_amla_rts_alignment`) is streamlit-free and unit-testable.

---

## Verify it worked

Three checks:

1. **The JSON exists** in the run dir and `n_rts_covered` matches the number of RTS articles your rules cite (`3/3` for the bundled `eu_bank` spec).
2. **STR acceptance is honest** — `str_acceptance_status` is `not_tracked`, not a fabricated rate.
3. **Determinism** — re-run the command against the same run dir; the JSON is byte-identical (`generated_at` is the manifest `as_of`, not a clock read).

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `RTS coverage: 0/3 articles` | No rule carries an `AMLR Art. 28(1)` / `AMLR Art. 19(9)` / `AMLD6 Art. 53(10)` citation | Add the citation to the relevant rule's `regulation_refs`; re-validate |
| `No manifest.json in <run-dir>` | You pointed at a directory that isn't an engine run dir | Pass a real `.artifacts/run-<TS>` dir (or run `aml run` first) |
| `precision` is `null` for every rule | No labels supplied — precision needs ground-truth true/false-positive labels | The run doesn't carry labels; supply them from your QA system if you need precision (the funnel + coverage are label-free) |
| A citation won't resolve to a URL | The AMLA citation isn't in `CITATION_URL_MAP` | The three RTS citations ship resolvable; for a novel one add a `url:` to the `regulation_refs` entry |

---

## Next steps

- [How to monitor model risk + per-rule drift](monitor-model-risk.md) — the sibling post-run report (`aml model-inventory` / `model_risk_report.json`); the AMLA pack reuses the same offline, deterministic, manifest-pinned shape.
- [`jurisdictions.md`](../jurisdictions.md) — the EU section, where the AMLA RTS effectiveness pack is the supervisory deliverable.
