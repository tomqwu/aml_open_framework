# How to use the Case Copilot for a case

> **When you need this:** You're working a case on the Case Investigation page and want a fast first draft — a summary of the alert, the likely typology, a starter STR/SAR narrative, the counterparty network, or a risk read with a recommended next action — without leaving the workspace or hand-rolling the boilerplate. The Case Copilot (#499) is the governed, in-page way to get those DRAFTS.
>
> **Prereqs:** A run loaded in the dashboard with at least one case. A GenAI backend selected via `AML_AI_BACKEND` — `ollama`, `openai`, or `azure_openai` for a live model; the default `template` gives canned scaffolding with no model call (useful offline). `program.ai_audit_log` (default `hash_only`) set per your privacy posture.
>
> **Time:** ~2 min per case.

The Case Copilot is **draft-generation only**. Every reply is an explicitly-marked DRAFT the investigator reviews — it is **never an auto-decision, never an auto-disposition**, and it never touches the engine run path. It reuses the same governed assistant as the sidebar AI advisor (`get_assistant` + `AssistantContext`/`AssistantReply`), so every action is audited to the run's append-only `ai_interactions.jsonl` (event `ai_case_copilot_action`) with the backend, model, and confidence recorded. This is the SR-26-2 carve-out in practice: GenAI augments a human investigator who stays accountable for the decision — the model proposes, the person disposes.

---

## Steps

### 1 · Choose a backend (governance-first)

The copilot inherits whatever backend the dashboard is configured for:

```bash
export AML_AI_BACKEND=ollama        # or: openai | azure_openai | template
```

- `template` (default) — deterministic canned scaffolding, no model call, no PII leaves the process. Use it offline or to see the action shapes.
- `ollama` — local model; PII transit stays on-box.
- `openai` / `azure_openai` — hosted model; confirm `program.ai_audit_log` and your data-egress posture first (`hash_only` keeps only a SHA-256 of each draft on disk; `full_text` retains the draft text).

The backend status (provider + whether a key is set + the spec's `ai_audit_log` mode) is visible on the AI Assistant page.

### 2 · Open the Case Investigation page and select a case

Navigate to **Case Investigation** (page 4) and pick the case you're working. The Case Copilot panel sits in the sidebar, scoped to that case — it sees the same entity profile, alert details, and transaction context the page renders.

### 3 · Pick a Copilot action (or ask freeform)

Choose one of the structured actions:

- **Summarize** — a concise read of the alert and the case so far.
- **Identify typology** — the likely typology(ies) the activity matches.
- **Draft STR-SAR narrative** — a starter regulatory narrative.
- **Counterparty network** — the counterparties and how funds move between them.
- **Risk & recommended action** — a risk read with a *suggested* next step.

Or type a freeform question for anything the structured actions don't cover.

### 4 · Review the DRAFT

The reply is labelled **DRAFT** and carries its **confidence** plus the **backend/model** that produced it. Read it critically: it's a starting point, not an answer. Confidence is an honesty signal, not a green light — a high-confidence draft still needs a human's eyes before anything is acted on.

### 5 · Edit and use it — the investigator decides

Take what's useful and discard the rest. For example, copy the **Draft STR-SAR narrative** into the case's narrative field as a seed, then edit it to match what you actually found. The disposition, the escalation, and the final narrative are **your** decision — the copilot never writes to the case state, never closes, escalates, or re-queues an alert.

---

## Verify it worked

Two checks:

1. **The reply is marked DRAFT** and shows a confidence value plus the backend/model name. If it doesn't, you're not looking at copilot output.
2. **The action is audited** — tail the run's `ai_interactions.jsonl` and confirm a row with event `ai_case_copilot_action`, the `backend`/`model`, `confidence`, and (under `hash_only`) the SHA-256 of the draft rather than its text:

   ```bash
   jq -c 'select(.event == "ai_case_copilot_action")' .artifacts/run-*/ai_interactions.jsonl
   ```

   No case in the ledger should have changed disposition as a result — the copilot is dashboard-only and never on the engine run path.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Replies look generic / canned | `AML_AI_BACKEND=template` (the default) — no model is being called | Set `AML_AI_BACKEND=ollama` (or `openai`/`azure_openai`) and restart the dashboard |
| Draft text isn't in `ai_interactions.jsonl`, only a hash | `program.ai_audit_log: hash_only` (the privacy-safe default) | Expected. Flip to `full_text` in the spec only after clearing it against your privacy posture — the spec change is itself the paper trail |
| Copilot panel is empty | No case selected, or no run loaded | Load a run and select a case on the Case Investigation page first |
| Worried the copilot might auto-close an alert | It can't — it generates DRAFTS only, never touches case state or the engine run path | Re-read the audit: every action is `ai_case_copilot_action`, the disposition stays whatever the investigator set |

---

## Next steps

- [Dashboard tour — Case Investigation (page 4)](../dashboard-tour.md) — the full case workspace the copilot is scoped to.
- [Spec reference — `program.ai_audit_log`](../spec-reference.md) — `hash_only` vs `full_text` governs what every copilot draft retains on disk.
- [How to export per-case evidence packs](export-case-pack.md) — once you've worked the case, hand a regulator the single-case ZIP.
