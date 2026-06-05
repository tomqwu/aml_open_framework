# How to stand up a GENIUS Act PPSI compliance program

> **When you need this:** You operate (or are building) a **permitted payment stablecoin issuer (PPSI)** and need an AML/CFT + OFAC sanctions program grounded in the joint FinCEN/OFAC NPRM — *Permitted Payment Stablecoin Issuer AML/CFT Program and Sanctions Compliance* (**Federal Register 2026-06963**, published 2026-04-10; comment deadline 9 June 2026). This recipe walks the richer NPRM-grounded `genius_ppsi_stablecoin` example end to end.
>
> **Prereqs:** A working install (`pip install -e ".[dev,dashboard]"`). The example spec is bundled at `examples/genius_ppsi_stablecoin/aml.yaml`. No external data needed — it runs on the deterministic synthetic generator.
>
> **Time:** ~10 min.

Governance up front: a PPSI is a BSA financial institution. The GENIUS Act PPSI NPRM (1) stands up a **new dedicated OFAC sanctions program at 31 CFR Part 502**, (2) confirms the PPSI registers as an MSB (31 CFR 1022.210), runs a risk-based AML/CFT program, and files SARs (31 CFR 1022.320), and (3) carries the FATF Travel Rule (Recommendation 16) on cross-border stablecoin transfers. Every rule in the spec maps to one of those obligations and every citation resolves via the regwatch citation map.

---

## Steps

### 1 · Validate the spec

```bash
aml validate examples/genius_ppsi_stablecoin/aml.yaml
# → OK ... 2 contract(s), 6 rule(s), 3 queue(s).
```

Two-layer validation runs: JSON Schema (structure) then Pydantic (cross-reference integrity — every rule's `escalate_to` resolves to a declared queue, every `source` to a declared contract).

### 2 · Run the engine at seed 42

```bash
aml run examples/genius_ppsi_stablecoin/aml.yaml --seed 42
```

On the canonical synthetic dataset this fires alerts across the stablecoin typologies (mixing/layering, rapid on-ramp/off-ramp cycling, structuring below the CTR threshold, OFAC SDN screening, adverse media). The `vasp_counterparty_exposure` rule needs KP/IR/MM counterparty rows to fire — it stays quiet on the default synthetic data, which is the realistic no-false-positive case.

### 3 · Read the rules

| Rule | Logic | Cites |
|---|---|---|
| `stablecoin_mixing_layering` | `custom_sql` — same-day fan-in then fan-out churn (≥70% pass-through, both legs ≥$15k) | GENIUS Act PPSI NPRM (FR 2026-06963), FIN-2019-G001 |
| `rapid_onramp_offramp_cycling` | `custom_sql` — mint then redeem within 24h, combined ≥$30k | GENIUS Act s.4, FIN-2019-G001 |
| `structuring_below_ctr_threshold` | `aggregation_window` — $5k–$9,999 deposits, ≥3 in 30d, ≥$20k | 31 CFR 1022.320, 31 CFR 1022.210 |
| `vasp_counterparty_exposure` | `custom_sql` — outbound stablecoin/wire to KP/IR/MM ≥$5k | FATF High-Risk Jurisdictions, FATF Recommendation 16 |
| `ofac_sdn_screening` | `list_match` (fuzzy 0.85) vs OFAC SDN | 31 CFR Part 502, OFAC SDN — virtual currency addenda |
| `adverse_media_screening` | `list_match` (fuzzy 0.85) vs adverse media | 31 CFR 1022.210, FIN-2019-G001 |

### 4 · Wire the OFAC SDN list

The `ofac_sdn_screening` rule reads the `sanctions` watchlist. Point it at your real OFAC SDN export (including the virtual-currency-address addenda) at deploy time — the bundled example uses a small demonstrative watchlist so the rule fires on synthetic data. A match obligates an immediate freeze, blocking report, and SAR under 31 CFR Part 502.

### 5 · Review the SLA + filing forms

The spec declares a `program.sla` block (`alert_disposition_days: 30`) — the engine records any open-alert-age or batch-lateness breach in `sla_report.json` (it never raises). Filing forms are `FINCEN_SAR` plus `FINCEN_CTR` (≥$10,000 aggregate-day trigger). Open the dashboard to inspect:

```bash
aml dashboard examples/genius_ppsi_stablecoin/aml.yaml
```

## Verify it worked

`aml run` prints a per-rule alert table and a metrics table; a non-zero total alert count confirms the program is detecting. Cross-check the citations resolve:

```bash
python -c "from aml_framework.compliance.regwatch import citation_url; print(citation_url('31 CFR Part 502'))"
```

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `ofac_sdn_screening` fires 0 alerts | Your watchlist has no fuzzy match ≥0.85 against any customer name | Confirm the `sanctions` list is loaded; lower the threshold only with sign-off |
| `vasp_counterparty_exposure` fires 0 | No KP/IR/MM `counterparty_country` rows in the data | Expected on default synthetic data — it fires on real cross-border flows |
| Citation does not resolve | Citation string not in the regwatch map | Use only citation strings present in `CITATION_URL_MAP` |

## Next steps

- [Add a new detection rule](add-a-rule.md) — extend the PPSI typology coverage.
- [Configure SLA monitoring](configure-sla.md) — tune the `program.sla` block.
- [Jurisdiction policies](../jurisdictions.md) — how the PPSI spec compares to the other US/FinCEN specs.
