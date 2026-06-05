# How to promote a rule across environments

> **When you need this:** You authored a rule in dev, want to send it to test for 2LoD validation, then to UAT, then to prod — without copy-pasting YAML and without firing the rule in prod before sign-off.
>
> **Prereqs:** A working rule in your spec. The rule lifecycle workflow shipped in PR-D3 / Round 28 (`Program.environment` + `Rule.environments`). `aml validate` succeeds on the spec.
>
> **Time:** ~5 min once you understand the model. Re-running it on every promotion is the point.

Spec-driven promotion: a rule declares which environments it's been approved for via `Rule.environments`, and the program declares which environment it's currently running in via `Program.environment`. The engine warns (or with `strict_environment_gating: true`, raises `EnvironmentGatingError`) when a mismatched rule fires.

---

## Steps

### 1 · Declare environments on the program

```yaml
program:
  name: community_bank_aml
  environment: dev               # dev | test | uat | prod
  strict_environment_gating: false   # flip to true once your promotion process is signing off rules
```

Greenfield deployments leave `environment: dev` until the promotion process is wired up. `strict_environment_gating: false` (the default) means mismatches log a warning; `true` raises and aborts the run.

### 2 · Mark each rule with the lanes it's approved for

```yaml
rules:
  - id: structuring_burst
    name: Cash structuring — 3+ deposits under threshold in 30d
    severity: high
    environments: [dev, test]     # NEW rule: dev + test only
    logic:
      type: aggregation_window
      ...
```

Brand-new rules typically ship `environments: [dev]` only. After 2LoD validation the list expands to `[dev, test]`, then `[dev, test, uat]`, then `[dev, test, uat, prod]` — each step is a spec PR with the corresponding sign-off in the PR description.

Once the spec lands, every active rule the runner reaches gets a gate-check event on `decisions.jsonl` via `promotion_audit_event()` — approved rules show `outcome: approved`, mismatched rules show `outcome: blocked` (strict) or `warn_only` (non-strict). **Strict-mode caveat**: when `strict_environment_gating: true`, the runner emits the event for the first blocked rule and **then raises `EnvironmentGatingError`**, so any active rules later in the spec aren't reached and don't get gate events that run. In non-strict mode every active rule gets one event. The grep recipes in §"Verify it worked" filter by outcome.

### 3 · Validate + run in the target lane

```bash
# Promote your spec to test:
sed -i.bak 's/environment: dev/environment: test/' aml.yaml
aml validate aml.yaml
aml run aml.yaml --seed 42
```

The runner emits a `promotion_audit_event()` for every active rule it reaches, regardless of approval — the `outcome` field differentiates `approved` (in this environment) from `blocked` / `warn_only` (mismatched). With strict gating enabled, the run aborts on the first mismatch, so active rules after it don't emit a gate event that run.

### 4 · Promote via spec PR

The promotion workflow is a normal git PR adding the next lane to the rule's `environments`:

```diff
- environments: [dev, test]
+ environments: [dev, test, uat]
```

Reviewers (2LoD MLRO, model risk, audit) sign off on the PR. The Rule Lifecycle dashboard page (`pages/51_Rule_Lifecycle.py`) surfaces this per-rule along with the `approval` column (honest placeholder until the signed-off-version store ships).

### 5 · Cut to prod

Final promotion:

```diff
- environments: [dev, test, uat]
+ environments: [dev, test, uat, prod]
```

Once the prod deploy picks up the spec and `strict_environment_gating: true` is set, the engine refuses to run rules that aren't approved for prod — the spec PR is now the audit trail.

---

## Verify it worked

Three checks per promotion:

1. **Gating events on the audit ledger** — `promotion_audit_event()` (`engine/promotion.py:88-111`) emits a gate event for every active rule the runner reaches. **In non-strict mode**, every active rule gets one event. **In strict mode** (`strict_environment_gating: true`), the runner emits the event for the first blocked rule and then raises `EnvironmentGatingError` — so an incomplete ledger after a strict-mode abort is expected, not evidence of full coverage. The `outcome` field carries one of three values:
   - `approved` — rule's `environments` includes the program env
   - `blocked` — mismatch + strict gating (run aborts after emitting)
   - `warn_only` — mismatch + non-strict gating (run continues; warning logged)

   ```bash
   # All mismatches (strict or warn-only):
   jq -c 'select(.outcome == "blocked" or .outcome == "warn_only")' \
     .artifacts/run-*/decisions.jsonl

   # Only the strict-mode blocks:
   jq -c 'select(.outcome == "blocked")' .artifacts/run-*/decisions.jsonl
   ```

2. **Rule Lifecycle dashboard page** — visit `pages/51_Rule_Lifecycle.py`; the rule's status column reflects the lifecycle stage. `model_tier`, `validation_cadence_months`, `rule_version` (16-hex SHA-256), and `risk_tier` show alongside.

3. **Replay the OLD spec, not the promoted one** — a promotion changes the spec content hash, so `rule_version` AND `decisions_hash` change too even when the alert population is unchanged. To verify "the same alerts would have fired," keep the pre-promotion spec snapshot in your audit pack and replay against THAT; the post-promotion run is a separate row in `run_manifests`.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Rule fires in `prod` despite not being on `environments: [..., prod]` | `strict_environment_gating: false` (default) — engine warns instead of blocking | Flip `strict_environment_gating: true` once your promotion sign-off process is wired up |
| Every rule fires the gating warning at startup | `Program.environment` left at `dev` but rules declared `[prod]` only | Either set `Program.environment` to match the deployed lane, or expand rule `environments` |
| `EnvironmentGatingError` on a rule that SHOULD be in this lane | Typo in the `environments` list (string instead of YAML list) | Fix the YAML; `aml validate` catches structural typos before runtime |
| Promotion PR merged but engine still skips the rule | Container hasn't picked up the new spec hash | Redeploy / restart the dashboard + API; the spec content hash drives `rule_version` |

---

## Next steps

- **Where do new rules come from?** `aml discover-typologies <spec> <run_dir>` is the upstream proposal lens: it profiles the *unexplained* population (customers no rule caught in that run), clusters them by shared anomalous shape, and writes `candidate_typologies.yaml` of PROPOSED rule stubs (`status: pending_promotion`). It is offline and human-gated — nothing auto-promotes. Review a proposal, then promote it through `add-a-rule.md` + the `environments:` ladder above.
- See [How to add a rule](add-a-rule.md) — the upstream `environments:` field on `Rule`.
- See [How to verify the audit chain](verify-audit-chain.md) — the **spec PR** is the promotion audit trail (the spec content hash changes; the git history records who approved). Subsequent runs against the new spec emit `promotion_audit_event()` gate-check events on `decisions.jsonl` (one per active rule per run) — those are the runtime evidence that the gate fired, not the promotion event itself.
- The Rule Lifecycle page (universally-routed, every persona) surfaces every rule's `status`, `model_tier`, `validation_cadence_months`, `rule_version`, `risk_tier`, and approval state. It does NOT yet show the `environments` list — adding that column is a small follow-up; for now verify via the gating-event grep above.
- For the cross-spec lifecycle (`active | experimental | deprecated`), see `Rule.status` in [`spec-reference.md`](../spec-reference.md).
