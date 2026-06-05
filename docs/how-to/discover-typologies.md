# How to discover candidate typologies from a run's unexplained anomalies

> **When you need this:** A run finished, your spec's deterministic rules caught what they're built for, and you want to know *what they're missing* — the customers whose behaviour stands apart from the population but no rule fired on. `aml discover-typologies` (PR / #496) profiles that **unexplained** population, clusters them by shared anomalous shape, and writes `candidate_typologies.yaml` of PROPOSED rule stubs for a human to review.
>
> **Prereqs:** A finished run directory under `.artifacts/` (so `alerts/*.jsonl` exists — that's how the tool learns who is already caught). `engine/typology_discovery.py::discover_candidates` is the canonical builder. The command is **offline** — it never runs in the engine path, fires an alert, or touches the audit ledger.
>
> **Time:** ~5 min, then as long as your review takes — the review is the point.

Governance up front: this command **proposes**, it does not promote. Every candidate lands as a rule stub with `status: pending_promotion`. Nothing mutates your spec automatically. The deterministic clustering (stdlib z-score + a shape signature, **no scikit-learn**) is a *discovery surface*, not a model in the regulated run path. A human reviews each proposal and either splices it into the spec or discards it — that approval is a hard stop.

---

## Steps

### 1 · Run the engine

You need a real run directory first — the candidates are computed *relative to* who the rules already caught.

```bash
aml run aml.yaml --seed 42
# → .artifacts/run-2026-06-05T10-15-30Z/  (with alerts/*.jsonl)
```

### 2 · Discover candidates from the unexplained population

```bash
aml discover-typologies aml.yaml .artifacts/run-2026-06-05T10-15-30Z \
  --output candidate_typologies.yaml
```

The tool loads the spec's data, computes per-customer features (count / sum / avg amount / unique counterparties / cross-border ratio), reads the run's `alerts/*.jsonl` to learn who is *already caught*, then clusters the **uncaught high-anomaly** customers by which features are anomalous.

On quiet synthetic data the default `--anomaly-z 2.0` floor can surface nothing (the planted positives are mostly caught, the background is, by design, quiet). Lower the floor to widen the net:

```bash
aml discover-typologies aml.yaml .artifacts/run-2026-06-05T10-15-30Z \
  --output candidate_typologies.yaml --anomaly-z 1.5
```

Other knobs: `--min-cohort-size` (smallest cohort that can become a candidate, default 3), `--data-source` / `--data-dir` (point at CSV/Parquet instead of the synthetic source), `--seed`, `--as-of`.

### 3 · Review the `candidates:` in the YAML

Each entry is a `pending_promotion` rule stub plus the metadata that explains *why* it was proposed:

```yaml
candidates:
  - id: candidate_typology_1
    status: pending_promotion
    metadata:
      size: 7                       # how many uncaught customers share this shape
      anomalous_features: [count, cross_border_ratio]
      label: high-frequency cross-border
    logic:
      type: aggregation_window
      ...
```

`size` tells you how much of the unexplained surface this candidate would cover; `anomalous_features` is the shape signature the cohort shares; `label` is the human-readable summary. Read every candidate — discovery is honest about coincidental cohorts, so not every proposal deserves promotion.

### 4 · Splice a chosen candidate into the spec

Pick the candidate(s) worth keeping and bring them into the spec:

- **By hand** — copy the stub's `logic:` into your spec's `rules:` block, give it a real `id` / `name` / `severity`, and (typically) ship it `environments: [dev]` only. This is the common path for a bespoke shape.
- **Via the catalogue** — if the candidate matches a curated typology, `aml typology-import <id> aml.yaml` installs the vetted version instead of the raw stub. (`aml typology-list` shows what's available.)

### 5 · Validate

```bash
aml validate aml.yaml
```

`aml validate` catches structural typos and broken cross-references before the rule ever runs.

### 6 · Promote via the normal approval path

A discovered candidate is just a new rule from here on — there is **no** auto-promotion. Run it through [How to add a rule](add-a-rule.md), then up the `environments:` ladder in [How to promote a rule across environments](promote-rule.md) with 2LoD / model-risk / audit sign-off on the spec PR. The candidate's discovery metadata is useful context to paste into that PR ("surfaced by `aml discover-typologies`, cohort size N, shape …"), but the approval is what makes it a rule.

---

## Verify it worked

Three checks:

1. **`candidate_typologies.yaml` exists** at `--output` (default `<run-dir>/candidate_typologies.yaml`) and every entry carries `status: pending_promotion`. The file is a *proposal artifact* — it is NOT one of the manifest-hashed run artifacts and is NOT on the audit chain (it's offline output, not run evidence).
2. **Determinism** — re-running `aml discover-typologies` on the same spec + run dir + flags produces byte-identical candidates. The clustering is pure stdlib z-score over a fixed feature set, so there's nothing stochastic to drift.
3. **No spec mutation** — `aml validate aml.yaml` is unchanged until *you* edit the spec. The discover step never writes to it.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `No alerts/ in <run-dir>` | You pointed at a directory that isn't a finished run | Run `aml run aml.yaml` first; pass the `.artifacts/run-*` dir it prints |
| Zero candidates on synthetic data | Default `--anomaly-z 2.0` floor is high for the quiet synthetic background | Lower it, e.g. `--anomaly-z 1.5`; also try a smaller `--min-cohort-size` |
| `No transaction rows resolved` | The spec has no `txn` / `transaction` data contract, or `--data-dir` points at the wrong place | Check the data contract id and the `--data-source` / `--data-dir` flags |
| A candidate looks like noise | Discovery is honest — coincidental cohorts surface too | That's the human gate working; discard it, that's a valid review outcome |

---

## Next steps

- [How to add a rule](add-a-rule.md) — turn a chosen candidate's `logic:` stub into a real, audited rule.
- [How to promote a rule across environments](promote-rule.md) — the `environments:` ladder + sign-off events that move it dev → test → uat → prod. The discover step feeds the *top* of this pipeline.
- **Dashboard:** the **Anomaly Discovery** page (page 49) is the same surface in the UI — it shows the per-customer z-score table and points back to this CLI to turn the surfaced anomalies into reviewable candidates.
