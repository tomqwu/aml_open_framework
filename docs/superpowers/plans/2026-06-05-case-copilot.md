# GenAI Case Investigation Copilot — Plan (#499)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** A governed Case Copilot panel on the Case Investigation page (4) that gives an investigator structured, case-scoped GenAI help — summarize / identify typology / draft narrative / network & risk — as human-reviewed DRAFTS, audited, under the SR-26-2 carve-out. Closes #499.

**Architecture:** MAXIMALLY REUSE the existing governed assistant. A new `dashboard/case_copilot.py` builds a case-scoped `AssistantContext` (case + customer + txn summary packed into `section_data`; no model change), calls `get_assistant(...).reply(...)` (existing template/ollama/openai/azure backends), renders the existing DRAFT framing, and audits to `ai_interactions.jsonl` via `reply_to_audit_dict` + `AuditLedger.append_to_run_dir` (event `ai_case_copilot_action`). **Stays entirely in the dashboard layer — NEVER the deterministic engine run path.** Governance is inherited: DRAFT-only (no auto-decision), full audit, backend/model recorded, confidence scored, `program.ai_audit_log` hash_only/full_text honored.

**Tech Stack:** Python 3.10+, the existing `aml_framework.assistant` (get_assistant, AssistantContext, AssistantReply, reply_to_audit_dict), Streamlit (lazy-imported in the UI fn only). Pure functions (context builder + prompts) carry NO module-level streamlit so they unit-test under `.[dev]`.

**Locked decisions:** dashboard-only (not the engine run); reuse the existing backends + audit + DRAFT (no new LLM integration, no AssistantContext schema change — case detail rides in `section_data`); structured canned prompts (deterministic prompt selection); DRAFT/human-reviewed only, never auto-dispositions; audited as `ai_case_copilot_action`.

---

### Task 1: Pure case-context builder + prompts (unit-testable, no streamlit)

**Files:** Create `src/aml_framework/dashboard/case_copilot.py`; Test `tests/test_case_copilot.py`.

`case_copilot.py` module-level imports: stdlib + `aml_framework.assistant.models` (AssistantContext) ONLY — NO `import streamlit` at module level (the UI fn lazy-imports it). The pure functions:
- `CASE_COPILOT_ACTIONS: tuple[str, ...]` = ("summarize", "typology", "draft_narrative", "network", "risk").
- `case_copilot_prompt(action: str) -> str` — returns the canned investigator question for each action (e.g. summarize → "Summarize this case in 2-3 sentences: who is the subject, what triggered the alert, and how severe is it?"; typology → "Which AML typology best fits this activity (structuring, layering, mule, sanctions evasion, pig-butchering, …) and why?"; draft_narrative → "Draft a concise STR/SAR narrative for this case from the evidence — WHO/WHAT/WHEN/WHERE/WHY."; network → "Which counterparties / related accounts are involved, and what does the flow pattern suggest?"; risk → "What is the highest-risk aspect of this case and what action do you recommend (escalate / file / close)?"). Raise ValueError on an unknown action.
- `build_case_copilot_context(*, page, action, case, customer, txns, spec_name, spec_jurisdiction, spec_regulator, run_id, persona=None) -> AssistantContext` — PURE. `case`/`customer` are dicts (or None), `txns` a list[dict]. Returns an AssistantContext with: page, persona, spec_*; selected_case_id = case["case_id"]; section_id = f"case_copilot.{action}"; section_title = f"Case Copilot · {action}"; section_data = a curated, JSON-safe dict (case_id, severity, queue, status, rule_id/name, customer_id, customer_risk_rating, customer_country, txn_count, total_amount, window_start/end, top channels) — ONLY values the LLM needs, no raw DataFrames. case_count=1. Tolerant of missing keys (use .get, default safe).

- [ ] Write failing tests: `case_copilot_prompt` returns a non-empty str for each action + ValueError on unknown; `build_case_copilot_context` produces an AssistantContext with the right selected_case_id, section_id=f"case_copilot.{action}", and section_data carrying case+customer+txn_count; tolerant of customer=None / empty txns; deterministic (same inputs → equal `model_dump()`).
- [ ] Implement. Tests green, lint, commit `feat(dashboard): pure case-copilot context builder + prompts (#499)`.

---

### Task 2: Copilot panel UI + Case Investigation page integration

**Files:** Modify `src/aml_framework/dashboard/case_copilot.py` (add the UI fn — lazy streamlit import inside it); Modify `src/aml_framework/dashboard/pages/4_Case_Investigation.py`.

- [ ] Add `case_copilot_panel(*, page: str) -> None` to case_copilot.py: `import streamlit as st` INSIDE the function (not module-level). Render in the sidebar (mirror `ai_panel`): a header "🔍 Case Copilot" + governance caption ("AI-assisted DRAFT — an investigator reviews; never an auto-decision"); a radio of the 5 actions + a freeform option; an "Ask" button. On Ask: pull `selected_case_id` + `df_cases`/`df_customers`/`df_txns`/`spec`/`run_dir` from session_state; build the case/customer/txns dicts; `ctx = build_case_copilot_context(...)`; `question = case_copilot_prompt(action)` (or the freeform text); `reply = get_assistant(os.environ.get("AML_AI_BACKEND","template")).reply(question, ctx)`; store in `st.session_state["case_copilot_transcript"][page]`; render via the existing reply renderer (reuse `_render_assistant_reply` from components.py, OR render DRAFT banner + text + confidence inline if importing it is awkward); audit: `reply_to_audit_dict(reply, full_text=(ai_audit_log=='full_text'))` + `AuditLedger.append_to_run_dir(run_dir, {"event":"ai_case_copilot_action","action":action,"question":question, **row}, jsonl_name="ai_interactions.jsonl")`. Wrap the whole thing in try/except → `st.error(...)` (never crash the page). Backend pill + PII note for openai (mirror ai_panel).
- [ ] In `pages/4_Case_Investigation.py`: after the page header / when a case is selected, call `from aml_framework.dashboard.case_copilot import case_copilot_panel; case_copilot_panel(page="Case Investigation")`.
- [ ] Parse-check both; convention tests (`test_section_explainer_migrated_pages.py`, `test_dashboard_page_header.py`) green; confirm case_copilot.py has NO module-level streamlit (so unit CI imports the pure fns fine — `grep -n "^import streamlit\|^from streamlit" src/aml_framework/dashboard/case_copilot.py` → empty). Lint. Commit `feat(dashboard): governed Case Copilot panel on Case Investigation (#499)`.

---

### Task 3: Docs

**Files:** CLAUDE.md, docs/dashboard-tour.md, docs/how-to/ (new `use-case-copilot.md`), docs/progress.md, docs/spec-reference.md (ai_audit_log already documents the audit mode — add a line noting case-copilot actions are audited too).

- [ ] CLAUDE.md Key Design Decision bullet: "**GenAI case copilot (#499):** a governed Case Copilot on the Case Investigation page reuses the existing assistant (`get_assistant` + AssistantContext/Reply + `ai_interactions.jsonl` audit) for case-scoped DRAFTS (summarize / typology / draft narrative / network / risk). Dashboard-only — NEVER the engine run path; SR-26-2 carve-out: human-reviewed DRAFT, audited, backend/model + confidence recorded, no auto-disposition." how-to recipe (set AML_AI_BACKEND; open a case; pick an action; review+edit the DRAFT; it's audited). dashboard-tour: Case Investigation sentence. progress.md #499 entry. README (optional — the copilot is a dashboard feature, not a CLI; mention only if natural).
- [ ] Docs-coverage tests green. Commit `docs(copilot): how-to + CLAUDE/tour/progress (#499)`.

---

### Task 4: Full CI gate

- [ ] `make ci-lint ci-unit ci-coverage` green; `make ci-e2e` green (Case Investigation renders; e2e readiness anchors are AI-independent so the copilot doesn't break them). Final whole-branch review → finishing-a-development-branch → PR (closes #499) → Codex → CI → merge → deploy reflex.

## Self-Review
- Spec: pure builder+prompts ✓ (T1), governed panel + integration ✓ (T2), docs ✓ (T3), gate ✓ (T4).
- Governance (SR-26-2): DRAFT-only/no auto-decision, audited (`ai_case_copilot_action`), backend/model + confidence recorded, ai_audit_log honored, dashboard-only (never the engine run path).
- Determinism boundary: copilot is non-deterministic GenAI but lives in the dashboard; replies audited not hashed-into-the-ledger; engine run untouched (no new import in runner.py).
- Dependency safety: pure fns (builder + prompts) carry NO module-level streamlit → unit-testable under `.[dev]`; the UI fn lazy-imports streamlit.
- Type consistency: `build_case_copilot_context(...)` returns the existing `AssistantContext`; `case_copilot_prompt`/`CASE_COPILOT_ACTIONS`/`case_copilot_panel` used consistently.
