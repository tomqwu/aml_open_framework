# How to promote a rule across environments

> **When you need this:** A rule has matured in `dev` / `test` and you need to move it to `uat` / `prod` with a signed-off audit trail.
>
> **Prereqs:** `Program.environment` declared in `aml.yaml` (PR-D3 #423). Rule has `environments: [...]` field populated.
>
> **Time:** ~5 min per promotion event.

The `engine/promotion.py` module gates rules by environment. Every rule-execution attempt emits a gate-check event on `decisions.jsonl` — examiners can prove the gate was consulted.

---

## Steps

> **TODO** — placeholder. The mechanism:
> 1. Update `Rule.environments` in `aml.yaml` to include the target lane
> 2. Emit a sign-off audit event (CLI command TBD)
> 3. With `Program.strict_environment_gating: true`, the runner raises `EnvironmentGatingError` on unapproved rule firings
> 4. With strict gating off, it `logger.warning`s instead but still records the gate-check on `decisions.jsonl`

---

## Verify it worked

> **TODO** — assertion that gate event appears on `decisions.jsonl` after promotion.

---

## Common problems

> **TODO** — common pitfalls (duplicate environment in list, missing sign-off event, wrong order).

---

## Next steps

- See [How to add a rule](add-a-rule.md) for the upstream `environments:` field.
- See [How to verify the audit chain](verify-audit-chain.md) to confirm promotion events flow into the chain.
