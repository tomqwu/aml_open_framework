# Crypto VASP — example spec

Minimal AML spec for a Virtual Asset Service Provider (VASP). Demonstrates
the framework's `network_pattern` rule type and entity-resolution layer in a
crypto context.

## What it covers

| Rule | Logic type | Typology |
|------|-----------|----------|
| `stablecoin_velocity_48h` | `aggregation_window` | Stablecoin layering with hold time < 48h (TRM 2026 trend) |
| `sanctioned_wallet_screening` | `list_match` | Customer wallet appears on OFAC / FINTRAC sanctions list |
| `nested_wallet_ring` | `network_pattern` | 3+ customer accounts sharing a wallet / device → nested-VASP service |
| `large_single_swap` | `aggregation_window` | $10k USD-eq single-day swap (LVCTR-equivalent) |

## Why this spec exists

Industry research scan (Apr 2026) flagged stablecoin layering as the new
structuring (TRM Labs reported ~84% of fraud-scheme inflows are stablecoins,
hold times collapsing under 48h). The standard regulatory frameworks were
built for fiat — this spec shows how the framework's existing primitives
(declarative aggregation windows, entity resolution, list matching) cover
crypto without changes to the engine.

## Citations

- **FATF Recommendation 16 (revised June 2025)** — Travel Rule + Confirmation
  of Payee for VASP-to-VASP transfers, including stablecoins.
- **FIN-2019-G001** — FinCEN's MSB guidance for convertible virtual currency.
- **PCMLTFR s.7.7** — Canadian record-keeping for dealers in virtual currency.
- **OFAC SDN — virtual currency addenda** — sanctions list now contains
  identified wallet addresses.

## Run it

```bash
aml validate examples/crypto_vasp/aml.yaml
# OK examples/crypto_vasp/aml.yaml — 2 contract(s), 4 rule(s), 4 queue(s).
```

## Sanctioned wallets list

`src/aml_framework/data/lists/sanctioned_wallets.csv` contains a small
sample of synthetic wallet addresses for the `sanctioned_wallet_screening`
rule's `list_match`. Production deployments should swap in the live
TRM/Chainalysis/OFAC sanctioned-wallet feed.
