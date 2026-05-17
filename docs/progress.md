# Project Progress

Snapshot of where the AML Open Framework is as of 2026-05-17. This document is a fact-based audit of what's shipped, not a roadmap or marketing piece. For "what's next?" see [`getting-started.md`](getting-started.md) and the [Changelog](../CHANGELOG.md).

> **Round 22 — Data Integration epic: more rails, fixtures, honest cloud-mock, richer UI** (#325–#327) shipped 2026-05-17: PR-A added modern payment rails (rtp / crypto / prepaid) + 3 planted typologies to the synthetic generator + canonical spec **additively — zero RNG re-base** (user-chosen over a dataset re-base), with 3 new rules (#325 / `v0.1.12`); PR-B added a deterministic `make fixtures` parquet/duckdb generator + an EXPLICIT, honestly-labelled local-mock path for the 8 cloud/warehouse source types (no credential fake) + a new ISO-20022 sample (#326, dev tooling — no deploy); PR-C surfaced both on the Data Integration page — per-source demonstrable-data status + a volume-by-channel chart (#327 / `v0.1.13`). Two Azure deploys; Codex caught a real rule-typology mismatch (the crypto pass-through rule was looser than its cash→crypto description), fixed before merge. Tests grew 2,357 → 2,400.
>
> _Prior:_ **Round 21 — non-blocking AI + real coverage gate + OS-following dark theme** (#316–#323, 2026-05-16 → 2026-05-17): async section explanations + real ≥99% gate (`v0.1.8`), then a 3-PR dark-theme arc — foundation (`v0.1.9`), theme-neutral charts after a determinism-driven pivot away from a reload-based dark bridge (`v0.1.10`), secondary-chrome sweep (`v0.1.11`).

---

## At a Glance

| Metric | Round 6 (2026-04-27) | Round 7 closed | Dashboard plan closed (2026-04-29) | Dashboard UX + GenAI push (2026-04-30) | Brand + UX consolidation (2026-05-01) | Round 10 — Data layer (2026-05-02) | Round 11 — Hardening + API + charts + docs (2026-05-04 → 2026-05-05) |
|---|---|---|---|---|---|---|---|---|
| Source code | 19,642 LOC across 18 modules | + ~2,500 LOC | + ~700 LOC | + ~3,500 LOC (PR-A → PR-L) | + ~2,650 LOC (PR-M → PR-T, 31 files) | + ~2,920 LOC (PR-DATA-1 → PR-DATA-10b, 19 files) | + ~1,700 LOC (PR #204-#211 + #217-#219, 26 files) |
| Tests | 991 | + ~110 | 1,161 passing | **1,750 passing** | **1,791 passing** | **1,848 passing** | **1,985 passing** (unit + API; +98 e2e collected separately) |
| Test files | 34 | 39 | 43 | 56 | 90 | 96 | 100 |
| Example specs | 7 | 9 | 9 | 9 | **10** | 10 | 10 |
| Unique regulation citations | 61+ | ~75+ | ~75+ | ~75+ | ~80+ | ~85+ (BCBS 239, FATF R.18, OSFI E-23/B-13, EBA outsourcing, Wolfsberg CBDDQ) | ~105+ (added PCMLTFR/OSFI/SEMA/FCA/PSR/OFSI) |
| Dashboard pages | 24 | 24 | 24 | **29** (+ Metrics Taxonomy, AI Assistant, screenshots-pending) | 29 (count unchanged; 31 page files inc. 2 nav surfaces) | **30** (+ Information Sharing) | **32** (sync + Data Integration in e2e; all counts unified) |
| Merged PRs (cumulative) | 18 (#46–#73) | + #74–#79 | + #80–#87 | + #150–#161 (PR-A → PR-L) | + #162–#168 (PR-M → PR-T) | + #177–#183 (PR-DATA-1 → PR-DATA-10b) | + #204-#211 (#216) + #217 + #218 + #219 |

---

## Module Surface

```
src/aml_framework/
├── api/              FastAPI REST layer (JWT auth, multi-tenant DB, rate limiting)
├── attestations/     MLRO sign-off ledger — hash-chained attestations.jsonl (Round 10)
├── cases/            Investigation aggregator, SLA timer, STR bundling, filing sidecars (Round 6/10)
├── assistant/        GenAI co-pilot (template/ollama/openai backends, sidebar on every page)
├── dashboard/        32-page Streamlit web app (mobile-responsive, multi-tenant, GenAI panel)
├── data/             Synthetic generator + 8 source loaders + ISO 20022 parser
│   ├── iso20022/     pacs.008, pacs.009, pain.001, pacs.004 ingestion (Round 5)
│   └── lists/        Sanctions, adverse media, sanctioned wallets, purpose codes
├── engine/           Rule executor on DuckDB, audit ledger with SHA-256 hash chain
├── generators/       SQL, DAG stubs, control matrix, STR narratives, board PDF,
│                     goAML XML, AMLA STR, MRM bundle, effectiveness pack
├── integrations/     Jira, Slack/Teams, SIEM/CEF connectors
├── metrics/          Metric evaluation engine + RAG bands + audience routing
├── models/           ML scoring callables for python_ref rules + travel-rule validator
├── narratives/       LLM-backed narrative drafting (Ollama, OpenAI backends)
├── pkyc/             Perpetual KYC trigger engine
├── sanctions/        OFAC SDN refresh + fuzzy match
├── spec/             JSON Schema + Pydantic validation + reusable rule library
└── vasp/             Public-data VASP attribution (Chainalysis alternative)
```

---

## Round-by-Round Delivery

### Round 5 — Payment Rails Ingestion (5 PRs, ~16 days)

Goal: ingest the messages banks actually move money with, after SWIFT's MX-only cutover (2025-11-22).

| PR | Feature | Driving signal |
|---|---|---|
| #56 | ISO 20022 `pacs.008` + `pacs.009` ingestion adapter | SWIFT MX-only cutover |
| #57 | FATF R.16 Travel Rule field validator (`python_ref` callable) | FATF Feb 2026 plenary deficiency call-out |
| #58 | ISO 20022 purpose-code typology library (4 reusable snippets) | ExternalPurpose1Code now mandatory |
| #59 | `pain.001` corporate-batch ingestion | Wolfsberg Feb 2026 correspondent-banking guidance |
| #60 | `pacs.004` payment-return + return-reason mining library (3 snippets) | UK PSR APP-fraud reimbursement (Apr 2026 full effect) |

**Result**: framework can natively consume every major ISO 20022 message type. Travel-rule completeness is automated. Two reusable spec-library files ship 7 typology rule snippets keyed to FATF / FinCEN / UK PSR / Wolfsberg guidance.

### Round 6 — Case Management as First-Class Surface (5 PRs, ~17 days)

Goal: make investigation (not alert) the unit of analyst work, per FinCEN's 2024 effectiveness rule.

| PR | Feature | Driving signal |
|---|---|---|
| #61 | Investigation aggregator (`cases/aggregator.py`) | FinCEN NPRM measures effectiveness per investigation |
| #62 | Multi-tenant dashboard surfacing (sidebar selector) | API had it; dashboard didn't |
| #63 | SLA timer + escalation engine (`cases/sla.py`) | FCA Mar 2026 Dear CEO letter on SAR backlogs |
| #64 | Case-to-STR auto-bundling (`cases/str_bundle.py`) | Wolfsberg Feb 2026 "submission-ready packages" |
| #65 | Investigations dashboard page #24 | Operator surface for the above |

**Result**: cases now aggregate into investigations with deterministic IDs. Live SLA tracking surfaces backlog state per-queue. Self-contained STR ZIPs bundle narrative + goAML XML + Mermaid diagrams + manifest hash. New dashboard page consolidates the workflow.

### Workflow Polish (4 PRs)

| PR | Feature |
|---|---|
| #67 | README refactor 582 → 123 lines + Getting Started guide + Dashboard Tour + Jurisdictions doc |
| #69 | `aml --help` typer/click compatibility fix; crypto_vasp doc gap |
| #70 | Mobile-responsive dashboard overlay (closes #66) |
| #71 | Workflow audit: executive font scale + 4 pages made interactive + missing pages registered |
| #72 | Synthetic data enriched with ISO 20022 fields + planted INVS positive |

**Result**: new-user onboarding path is 15 minutes. Mobile viewports work. Executive personas (SVP/CTO/CCO/VP/Director) get auto-scaled fonts. Default `aml run --seed 42` demo now exercises all Round 5/6 features.

### Round 7 — Research-driven defensive layer (5 PRs, ~21 days)

Goal: ship the top-5 features ranked by impact ÷ effort in the [2026-04 competitive positioning research](research/2026-04-competitive-positioning.md). All five anchored to a 2026 regulatory clock the research surfaced as load-bearing.

| PR | Feature | Driving signal |
|---|---|---|
| #74 | Regulatory-change diff watcher (`compliance/regwatch.py`) | FinCEN BOI Mar 2025 narrowing + April 2026 NPRM 12-month tail |
| #75 | AMLA STR/RTS effectiveness telemetry pack (`metrics/outcomes.py`) | AMLA RTS due 2026-07-10 + FinCEN NPRM enumerates same metrics |
| #76 | TBML + UK APP-fraud example specs | FATF Feb 2026 plenary + PSR Apr 2026 full-effect reimbursement |
| #77 | PSD3 / Verification-of-Payee adapter (DRAFT) | PSD3/PSR Council/Parliament agreement end-Q2 2026; VoP applies +24 months |
| #78 | FINTRAC pre-examination audit pack (`generators/audit_pack.py`) | FINTRAC January 2026 examination manual update |

**Result**: framework now has a defensive layer that sits *above* the spec — drift detection against silently-changing regulator pages, regulator-format effectiveness JSON, jurisdiction-templated examination evidence packs. This is the layer commercial vendors don't ship because they own the rule library themselves; the framework needs it precisely because it doesn't.

**Cross-feature integration** (closed in Dashboard Workflow & Design plan, 2026-04-28):
- Dashboard page surfacing the outcomes funnel ✅ Phase B-2
- Dashboard panel for regwatch drift findings ✅ Phase B-2
- One-click audit-pack download from Audit & Evidence ✅ Phase B-3
- VoP outcomes panel on Sanctions Screening ✅ Phase B-3

### Dashboard Workflow & Design plan (8 PRs, 2026-04-27 → 2026-04-28)

Goal: ensure proper workflow + design across the dashboard. Audit identified 5 hidden modules, broken cross-page navigation, muddled persona arcs, and crash-prone empty-state behavior.

| PR | Phase | Feature |
|---|---|---|
| #80 | A | Cross-cutting helpers: `link_to_page`, `read_param`, `consume_param`, `severity_color`, `sla_band_color`, `empty_state` |
| #81 | B-1 | SLA timer + STR-bundle download on case-facing pages (#4, #21, #17) |
| #82 | B-2 | Effectiveness funnel on Executive Dashboard + regulation-drift panel on Audit & Evidence |
| #83 | B-3 | FINTRAC audit-pack download on Audit & Evidence + VoP outcomes on Sanctions Screening |
| #84 | C | Cross-page drill-downs / deep links — Alert Queue + Network Explorer + Customer 360 + Executive |
| #85 | D | Persona workflow rebalance — every persona ≤8 pages, coherent task arcs |
| #86 | E | Empty-state defenses on engine-side pages (#5, #10, #11) + design consistency test guards |
| #87 | E follow-up | `risk_color()` resolver + 7 pages migrated off inline color dicts; test ALLOWED set drained |

**Result**: every Round-6/7 module is now reachable from the dashboard (was the original Phase B goal). Cross-entity drill-downs eliminate the audit's worst dead-ends (~20-30s saved per drill, dozens per shift). Three pages that crashed on degenerate specs now degrade gracefully. Color/SLA palette has a single source of truth — any new inline color dict fails CI. Tests grew 1089 → 1161 across the 8 PRs.

### Dashboard UX + GenAI push (12 PRs, 2026-04-30)

Goal: close the remaining clickability/colour/cross-link gaps from a fresh page-by-page audit, then surface the dashboard's existing GenAI substrate as a co-pilot on every page. Single day, 12 PRs auto-merging on green per the project memory rule.

| PR | Workstream |
|---|---|
| #150 | PR-A · Row-click drill-through across 5 triage tables (Alert Queue, Customer 360, My Queue, Investigations, BOI Workflow) |
| #151 | PR-B · Severity + RAG cell colouring on 6 read-only tables (centralised Styler helpers — `severity_cell_style`, `rag_cell_style`, `metric_gradient_style`, `event_type_cell_style`) |
| #152 | PR-C · Cross-page navigation + research-link sweep — `see_also_footer` on 6 pages |
| #154 | PR-D · Empty-state polish — `empty_state()` helper applied across 6 pages |
| #153 | PR-E · Chart palette + tooltips + SLA-band shading + best-F1 annotation |
| #155 | PR-F · Regulation citation hyperlinks via new `citation_link()` helper |
| #156 | PR-G · KPI card drill-through on My Queue / BOI Workflow / Alert Queue |
| #157 | PR-H · ID-linking sweep + Tuning Lab `rule_id` deep-link reader |
| #158 | PR-I · **Metrics Taxonomy** catalogue page (#28) — sister to Typology Catalogue, browseable definitional view of every metric the spec declares |
| #159 | PR-J · `dashboard-tour.md` drift fix + `test_dashboard_tour_coverage.py` prevention pattern. Closed Issue #68. |
| #160 | PR-K · **GenAI Assistant MVP** — sidebar panel on every dashboard page via a single line in `page_header()`. New `assistant/` sibling module to `narratives/` with template/ollama/openai backends. Spec-configurable audit log via `program.ai_audit_log: hash_only \| full_text`. New page #29 for backend status + transcript + run-level audit trail. |
| #161 | PR-L · Docs sync (this snapshot, README, spec-reference) |

**Result**: dashboard now ships with click-everywhere navigation, a coherent colour discipline (RAG / severity / SLA from centralised tokens, no inline hex), an audit-doc-defendable Metrics Taxonomy reference, and a GenAI co-pilot that mounts on every page without per-page edits. The `narratives/` substrate that previously powered only the Case Investigation STR drafter is now reused for the assistant — same Citation model, same backend factory, same audit-log discipline. Tests grew 1,646 → 1,750 (+104) across the 12 PRs.

### Brand + UX consolidation (7 PRs, 2026-05-01)

Goal: port the landing-site brand DNA (deck → dashboard CSS), then absorb the regressions that surfaced once the topbar / Today-hero rebuild went live. Smaller wave than PR-A→L; mostly CSS, fixes, and one e2e expansion.

| PR | Workstream |
|---|---|
| #162 | PR-M · Port deck DNA to live CSS (typography scale, spacing, accent ramp) |
| #163 | PR-N · Landing-site brand applied — wordmark + cream/orange palette |
| #164 | PR-O · Preserve sidebar expand control after collapse (regression from N) |
| #165 | PR-Q · Landing-style topbar + ivory sidebar + Today hero |
| #166 | PR-R · Fix Today cards crashing for VP / SVP / Director / Developer / FinTech personas (KeyError on persona-filtered metrics) |
| #167 | PR-S · Fix `link_to_page()` crash when target page is hidden by persona filter |
| #168 | PR-T · e2e persona × page coverage matrix + HTML-leak detector + KPI render fix |

**Result**: dashboard chrome now matches the landing-site brand. Two persona-side crashes that surfaced after the topbar/Today-hero rebuild are fixed and protected by a 31×12 persona-page e2e coverage matrix. The HTML-leak detector catches a class of bug where Streamlit components render unrendered Markdown/HTML strings into the page (a regression vector that's easy to introduce when porting CSS-heavy components). Tests grew 1,750 → 1,791 (+41) across the 7 PRs; test files went 56 → 90 (the e2e expansion split into per-persona modules). Three follow-up README polish commits (`Where this fits in your stack`, `In-bank, not SaaS`, Quickstart venv guidance) shipped directly to main outside the PR cadence.

### Round 10 — Data layer hardening (7 PRs, 2026-05-02)

Goal: close the gap between the "Data is the AML problem" whitepaper's claims (`docs/research/2026-05-aml-data-problem.md`, shipped in PR #174) and what the code actually backs. A code audit against the doc found 3 STRONG / 5 PARTIAL / 3 STUB verdicts across 11 DATA-N sections; this round addresses the 6 with material gaps.

| PR | Workstream | DATA-N | Whitepaper claim before / after |
|---|---|---|---|
| #177 | PR-DATA-1 · Fail-closed contract validation | DATA-1 | "Validator fails closed" — partial → **strong** |
| #178 | PR-DATA-2 · pKYC integration + per-attribute freshness pinning (`max_staleness_days` + `last_refreshed_at_column`) | DATA-2 | "Per-attribute freshness pinning" — stub → **strong** |
| #179 | PR-DATA-4 · Per-decision audit metadata + `walk_lineage()` helper | DATA-4 | "Walk-back from any KPI to producing run + rule version + spec hash + input file hashes" — partial → **strong** |
| #180 | PR-DATA-9 · Real STR/SAR filing-latency capture (filing sidecars) | DATA-9 | "STR filing-latency p95 is a first-class metric" — proxy → **real wall-clock** |
| #181 | PR-DATA-8 · MLRO attestation workflow + `aml run --strict` gate | DATA-8 | "MLRO signs against Manifest hash" — stub → **strong** (hash-chained `attestations.jsonl`) |
| #182 | PR-DATA-10a · `information_sharing` spec syntax + `aml share-pattern` / `aml verify-pattern` CLI | DATA-10 | "Cross-bank info-sharing reference surface" — sandbox-only-as-library → **policy boundary in spec + CLI seam** |
| #183 | PR-DATA-10b · Information Sharing dashboard (page #31) | DATA-10 | Operational view (declared partners + recent share-pattern artifacts) |

**Result**: 6 DATA-N sections promoted from stub/partial to strong. New module `attestations/` (17 modules total). New engine submodule `engine/freshness.py`. New cases sidecar `cases/<case_id>__filing.json`. Three new CLI commands (`attest`, `share-pattern`, `verify-pattern`); two new audit-event types (`contract_violation`, `pkyc_trigger`). Audit-ledger schema bumped to version 2 with `rule_version` stamped on every `case_opened` event. Tests grew 1,791 → 1,848 (+57) across 6 new test files; test files went 90 → 96. The `aml run --strict` opt-in flag refuses to execute against unattested specs — the first concrete Manifest-version gate the framework ships.

The whitepaper's three remaining claims (DATA-3 reconciliation, DATA-5 sovereignty, DATA-11 spec-as-data-contract) were already STRONG; DATA-6 (AI presumes data) is closed transitively by PR-DATA-1's fail-closed validation; DATA-7 (Engineering vs Compliance ownership) is technical-pattern-strong via the data-contract architecture, with the residual gap being organisational and out of code scope.

### Round 11 — Hardening + API + charts + docs (10 PRs, 2026-05-04 → 2026-05-05)

Goal: close the residual gaps surfaced by a fail-closed / compliance-posture review (#204-#211), finish the chart-library migration started in Round-9, harden the REST API surface for production deploys, and unify the 21 stale page/test/jurisdiction counts that had drifted across docs and the landing site.

| PR | Workstream |
|---|---|
| #213 | `fix(api)`: gate demo auth in production — refuse demo-mode credentials when `ENV=production` |
| #214 | `fix(data)`: fail closed on unloadable data contracts (raise instead of silent fallback) |
| #215 | `fix(engine)`: fail closed on `python_ref` scorer failure by default — opt-in to soft-fail |
| #216 | Compliance hardening — gap-review batch closing #204-#211: SQL proxy dispatch correctness, strict CSV row validation, dashboard page-inventory drift test, jurisdiction overclaim cleanup, citation-URL completeness (PCMLTFR/OSFI/SEMA/FCA/PSR/OFSI), sanctions alias persistence, audit/filing JSONL append-only ledger, dashboard data-source mode tracking |
| #217 | `fix(charts)`: finish ECharts + AG Grid migration — zero Plotly references, zero `st.dataframe` calls remain |
| #218 | `fix(api)`: harden uploads + OIDC — strict audience validation, configurable artifact root for run persistence, Helm `values.yaml` keys + deployment template, `.env.example` + deployment.md updates, +89 lines of new API tests |
| #218 | `docs`: refresh all docs and landing site — 21 stale metrics unified across README/landing/dashboard-tour/getting-started/CONTRIBUTING/CHANGELOG/progress.md (page count 31→32, test count 1,790/1,910/1,850 → 1,980, jurisdictions claim → "5 jurisdictions with 10 bundled specs", deck slide page-counts) |
| #219 | `fix(ci)`: filter the exact transient browser-only `Failed to fetch` pageerror in dashboard e2e while preserving Streamlit exception and other pageerror failures |

**Result**: the framework now fails *closed* across three more boundaries (demo-auth in prod, data-contract load, python_ref scorer error) — completing the policy that started with PR-DATA-1. Every chart and every table on the dashboard is now ECharts / AG Grid (no Plotly, no `st.dataframe`). The REST API artifact-root configuration unblocks production K8s deploys where pod ephemerality requires runs to persist outside `/tmp`. Twenty-one stale numeric claims across docs were reconciled in a single sweep so future drift is detectable; CI flake on transient browser fetch errors no longer noise-trips the e2e gate. Tests grew 1,848 → 1,985 (+137) across 10 PRs.

### Round 12 — End-to-end lineage (11 PRs, 2026-05-07)

Goal: close the gap between "we have a hash-chained audit log" and "we can walk an examiner from any alert to its source row." Eleven PRs across backend (Phase A), dashboard surfacing (Phase B), a new dedicated page (Phase C), and marketing (Phase D).

| PR | Phase | Workstream |
|---|---|---|
| #222 | A | PR-LIN-1 · Surface rendered SQL via `walk_lineage()` (lifts `rules/<rule_id>.sql` into the chain dict) |
| #223 | A | PR-LIN-2 · Stamp source path + schema_columns + schema_hash on `record_input()` (8 source types via new `infer_source_paths()` helper) |
| #224 | A | PR-LIN-3 · Stamp `rule_version` on every decision event (escalate / closed / rule_failed), not just `case_opened` |
| #225 | A | PR-LIN-4 · Capture `matched_row_ids` per alert across `aggregation_window` / `custom_sql` / `list_match` / `network_pattern` (python_ref deferred — would break callable contract) |
| #226 | B | PR-LIN-5 · Audit & Evidence — SQL viewer + matched-row grid + source-provenance columns on the existing lineage walk-back panel |
| #227 | B | PR-LIN-6 · Case Investigation — "Why this fired" panel above Transaction Timeline (matched-row count + severity + rule_version + collapsible rule SQL) |
| #228 | B | PR-LIN-7 · Data Integration — Source → Contract → DuckDB Table mapping section; DATA-3 / DATA-4 status flipped from "stub" to "shipped" |
| #229 | C | PR-LIN-8 · New Lineage Explorer page #32 — Mermaid graph + run anchors + source provenance + rule SQL + matched rows + decision timeline + JSON download. Registered in app.py + e2e PAGES + analyst persona |
| #230 | D | PR-LIN-9 · Landing page — third hero "Trace every alert. Down to the row." + new research card + `#/research/lineage` hash route |
| #231 | D | PR-LIN-10 · `research/lineage.html` deep-dive — 7-link evidence chain, 12 stamped fields, regulator anchors (BCBS 239 P3-P5, FinCEN April 2026 NPRM, SR 26-2, OSFI E-23) |
| #232 | D | PR-LIN-11 · New technical slide `24-lineage-walkback.html` (Act IV) + by-the-numbers slide refresh (test count 1,632 → 2,000+, pages 26 → 32, specs 9 → 10, CLI 24 → 38, licence MIT → Apache 2.0) |

**Result**: the audit question "show me why this alert fired" now has a one-paste-box answer. The 7-link chain (source file → contract → DuckDB table → rule → alert with `matched_row_ids` → case → STR) is hash-stamped end-to-end, reproducible from spec + data + as_of, and downloadable as JSON for offline review. Three existing dashboard pages got the relevant slice of the chain inline; the new Lineage Explorer page consolidates the deeper drill. The 12-field per-decision payload is now the framework's documented audit shape. DATA-3 (cross-system reconciliation) and DATA-4 (lineage walk-back from KPI) are shipped, not stubs. Tests grew 1,985 → ~2,020 (+35) across 11 PRs.

### Round 13 — Lineage coverage gaps · dashboard, exports, CLI, API (9 PRs, 2026-05-07)

Goal: close the gap between "the lineage primitives exist" and "every surface a regulator, analyst, or integration consumer might touch shows the chain." A 3-pronged audit after Round 12 found that 14 of 32 dashboard pages carried zero lineage, all 3 regulator-facing exports were lineage-blind, and there were no CLI commands or API endpoints for lineage at all.

| PR | Phase | Workstream |
|---|---|---|
| #237 | E | PR-LIN-12 · Triage path lineage — Alert Queue + My Queue + Analyst Review Queue gain `Matched rows` + `Rule version` columns / Source-lineage expander; Case Investigation deep-links to Lineage Explorer |
| #238 | E | PR-LIN-13 · Entity-context lineage — Investigations + Network Explorer + Customer 360 gain inline columns + per-case Lineage Explorer deep-links |
| #239 | E | PR-LIN-14 · Analytical-arc lineage — Rule Performance gains `Rule version` (via `rule_version_hash`) column; Sanctions Screening gains `Source rowid` from `matched_row_ids[0]`; Run History + Tuning Lab gain Lineage Explorer pointers |
| #240 | E | PR-LIN-15 · Headline + AI lineage — Today + Executive Dashboard + AI Assistant gain Lineage Explorer entry-points; AI Assistant citations get a "Verify against audit trail" deep-link per `referenced_case_id` |
| #241 | F | PR-LIN-16 · STR bundle `manifest.json` carries a `case_lineage` block (rule_version + matched_row_ids + per-contract source_path/schema_hash/content_hash). Regulator extracting the ZIP can answer "which rule version, which source rows" without re-running |
| #242 | F | PR-LIN-17 · Audit pack ships a new `case_lineage_summary.json` section. FINTRAC examiner gets the chain per case from the bundle alone |
| #243 | F | PR-LIN-18 · Effectiveness pack — Control Output Quality pillar gains `alerts_by_rule_with_lineage` finding (per-rule alert_count + rule_version + sample_matched_rows). Closes FinCEN April 2026 NPRM standard's "show your work" gap on aggregate metrics |
| #244 | G | PR-LIN-19 · CLI — `aml lineage <case_id>` (JSON or table) + `aml verify-decisions [--expected-hash]`. Wraps `walk_lineage()` and `AuditLedger.verify_decisions()` for scriptable use; tamper detection exits non-zero |
| #245 | G | PR-LIN-20 · API — `GET /api/v1/runs/{run_id}/cases/{case_id}/lineage`. Auth gated; tenant-isolated; 404s on unknown run / missing run_dir / unknown case_id; 401 without auth |

**Result**: lineage is now reachable from every dashboard surface (14 pages updated), every regulator-facing export (STR bundle / FINTRAC audit pack / FinCEN effectiveness pack), the CLI (`aml lineage`, `aml verify-decisions`), and the API (`GET .../cases/{id}/lineage`). The audit chain is no longer "primitives in the data" — it's "addressable from anywhere a consumer might be." Tests grew ~2,020 → 2,050 (+30) across 9 PRs.

### Round 14 — Final lineage coverage audit (2 PRs, 2026-05-07)

Goal: after Round 13, audit every dashboard page for lineage suitability and close real gaps. User asked for completeness; the honest answer is *coverage by relevance, not by URL count*. A 3-pronged audit of the 16 pages NOT touched by Rounds 12+13 produced this verdict:

| PR | Workstream |
|---|---|
| #249 | PR-LIN-23 · 5 case-aware pages get lineage hooks: Risk Assessment (row-click drill → Alert Queue), Model Performance + Comparative Analytics + FinTech Cockpit + Metrics Taxonomy (`→ Open Lineage Explorer` pointer). 12 new ALLOWED_GRACEFUL_GAPS entries for personas seeing these pages without Lineage Explorer in their nav. |
| #250 | PR-LIN-24 · Round 14 docs section (this entry) + CHANGELOG block explaining the coverage policy. |

**Pages explicitly excluded — 10 pages** that carry no case-level domain to walk back from. Listed here so future audits don't re-litigate:

| Page | Why no lineage |
|---|---|
| **0_Welcome** | Orientation router; pure persona routing, zero case context |
| **2_Program_Maturity** | Spec-level aggregate posture; not case-driven |
| **8_Framework_Alignment** | Prescriptive regulator-mapping matrix; no case evidence |
| **9_Transformation_Roadmap** | Project planning; not investigation |
| **11_Live_Monitor** | Ephemeral simulator; alerts not persisted to audit trail |
| **14_Data_Quality** | SRE / data-contract focus; validates sources, not subjects |
| **16_Rule_Tuning** | What-if threshold tool; not tied to actual alerts |
| **20_Spec_Editor** | YAML authoring; cases live downstream once rule deploys |
| **27_Regulator_Pulse** | Regulator-news doctrine; cross-links to responding pages already |
| **31_Information_Sharing** | Cross-bank policy/config; obfuscated, no case mapping by design |

**Already covered before this round (1 page):** 25_BOI_Workflow drills via Customer 360, which has the Round-12 lineage panel. Chain is complete.

**Result**: every page where lineage is *meaningful* now reaches Lineage Explorer. The 10 excluded pages remain link-free deliberately — adding generic pointers there would dilute the meaning of "lineage." After Round 14, the lineage workstream is **closed.** Future page additions follow the established pattern (link_to_page with case_id when available, generic pointer otherwise). Tests grew 2,050 → 2,055 (+5) across 2 PRs.

### Round 15 — Azure bank-deploy stack (4 PRs, 2026-05-07)

Goal: make the framework deployable on Microsoft Azure with zero static secrets. After Rounds 12–14 closed the lineage workstream, the user asked to integrate with Azure platform tools/systems. Azure spans 7+ surfaces (data, identity, secrets, deploy, AI, SIEM, governance); user picked all four high-value buckets and split them across two rounds — bank-deploy now (Round 15), AI + Sentinel + Purview later (Round 16).

| PR | Workstream |
|---|---|
| #251 | PR-AZ-1 · Data sources — `azure_blob` + `adls` (DuckDB azure extension over `abfss://` URIs) + `synapse` + `azuresql` (pyodbc with ActiveDirectoryMsi auth on AKS workload identity). 4 new dispatch branches in `resolve_source()` + 4 new `infer_source_paths()` cases so the Round-12 lineage chain picks up Azure-sourced runs unchanged. New `[azure]` extras in pyproject.toml. |
| #252 | PR-AZ-2 · `aml_framework.secrets.SecretsProvider` — Key Vault first, env-var fallback. DefaultAzureCredential picks up workload identity on AKS; falls back gracefully when SDK init fails. JWT_SECRET, OPENAI_API_KEY, demo-user passwords all routed through the provider. Naming translation `_` → `-` for Key Vault compatibility. |
| #253 | PR-AZ-3 · AKS Helm chart additions — `azure:` block in values.yaml (5 optional fields), workload-identity ServiceAccount + pod label rendered conditionally, AZURE_KEY_VAULT_NAME / AZURE_STORAGE_ACCOUNT_NAME / AZURE_SYNAPSE_CONN / AZURE_SQL_CONN env vars threaded to API + dashboard pods. New `values-azure.example.yaml` with az CLI cookbook. New "Deploying on Azure / AKS" section in `docs/deployment.md`. |
| #254 | PR-AZ-4 · Round 15 docs sync (this entry) — progress.md + CHANGELOG + README + architecture.md. |

**Result**: a regulated bank with an Azure tenant can deploy this on AKS today. Workload identity removes static credentials end-to-end; Key Vault houses the JWT signing key + OpenAI API key; Entra ID OIDC handles API auth via the existing generic OIDC support (no code changes — config only). Lineage chains from Round 12 work unchanged on Azure-sourced runs (`source_path: azure_blob:abfss://...`). Tests grew 2,055 → 2,076 (+21) across 4 PRs.

**Round 16 (queued, not shipped):** Azure OpenAI as a 4th assistant backend; Microsoft Sentinel SIEM via Log Analytics Data Collector; Azure Monitor / Application Insights via OpenTelemetry; Microsoft Purview lineage push via Atlas API. The Purview piece is the **differentiated** one — pushing `walk_lineage()` chains to Purview means AML lineage shows up in the same governance pane as a bank's other data assets.

### Round 16 — Land on the user's Azure backbone, Phase A (4 PRs, 2026-05-07)

Goal: deploy the framework on the user's prebuilt landing zone at [tomqwu/cloud_landing_zone_for_ai_coding](https://github.com/tomqwu/cloud_landing_zone_for_ai_coding). Round 15 shipped the AKS Helm chart for self-managed Azure / on-prem K8s; this round adds the **Container Apps** path that the landing zone constrains us to.

Surprise constraint: the landing zone's `CLAUDE.md` explicitly forbids AKS — *"compute: only Azure Functions Flex Consumption, Container Apps, or Static Web Apps."* Round 15's Helm chart still ships for non-landing-zone deployments; Round 16 Phase A adds an alternative.

| PR | Workstream |
|---|---|
| #255 | PR-AZ-5 · Terraform deployment module under `deploy/terraform/` calling `module.onboard` from the landing zone (vends RG + UAMI + per-app Key Vault + FICs). Provisions Postgres Flexible Server B1ms with Entra-ID-only auth, Container Apps for API + dashboard with UAMI assigned, diagnostic settings → platform Log Analytics workspace, Key Vault secret placeholders for JWT-SECRET / OPENAI-API-KEY (with `lifecycle.ignore_changes` so operator-set values survive). |
| #256 | PR-AZ-6 · GitHub Actions pipeline `deploy-azure-landing-zone.yml` — three jobs: `plan` (PR comments) → `build_and_push` (ACR via OIDC) → `apply` (gated by `platform-prod` Environment, with revision-rollover nudge + `/health` smoke check). All auth via federated identity credential — no secrets stored in the repo. **Removed in Round 18 (PR #295):** Azure deploy is now local-only; CI does not hold Azure credentials. |
| #257 | PR-AZ-7 · OpenTelemetry → Azure Monitor wiring. New `src/aml_framework/observability/` module with `init_observability()` — lazy-imports `azure.monitor.opentelemetry`, no-op when `APPLICATIONINSIGHTS_CONNECTION_STRING` is unset, idempotent + exception-swallowing. Wired from `api/main.py` + `dashboard/app.py`. New `azure-monitor-opentelemetry` in `[azure]` extras. |
| #258 | PR-AZ-8 · Round 16 Phase A docs sync (this entry). |

**Result**: a `terraform apply` against the user's tenant lands the framework end-to-end on Container Apps + Postgres + per-app Key Vault, with the Round-12 lineage chain intact (case_id → Lineage Explorer renders against cloud-deployed dashboard) and the Round-15 Azure data sources working unchanged. Cost ~$33/mo idle on top of the landing zone's $5 baseline. Tests grew 2,076 → 2,084 (+8) across 4 PRs.

**Phase B (queued, not shipped):** Azure OpenAI as 4th assistant backend, Microsoft Sentinel via the platform Log Analytics workspace, Microsoft Purview lineage push. Lives in a future plan.

### Round 17 — Plant coverage + persistence asymmetry + housekeeping (9 PRs, 2026-05-08 → 2026-05-09)

Goal: close the MRM-trustability gap on under-covered specs (us_rtp_fednow, trade_based_ml, uk_app_fraud) by planting ground-truth positives that match each rule's window/threshold semantics, plus a persistence-layer cleanup that surfaced from Azure deployment work.

`#272` was bundled into `#271` and `#280` into `#279` via stacked-PR cascades, so 7 squash commits land on main for these 9 PR numbers.

| PR | Workstream |
|---|---|
| #271 | Flip persistence backend precedence to postgres > cosmos in `_active_backend()`. Helm `api-deployment.yaml` + `dashboard-deployment.yaml` mirror the flip so what `kubectl describe` shows matches what the Python runtime picks under dual-config. One-time WARN log when both `DATABASE_URL` and `COSMOS_ENDPOINT` are set so an operator migrating Cosmos→Postgres sees the silent backend switch in startup logs. New `TestCrudFunctionsRouteToPostgresUnderDualConfig` covers all 7 public CRUD funcs. |
| #272 | (bundled into #271 via stacked-PR cascade) Dashboard startup-log test class (`TestDashboardStartupLogsBackend`) verifies the dashboard pod's `Persistence backend: %s` line emits to the `aml.dashboard` logger. Class-scoped `_restore_sys_modules` fixture prevents streamlit imports leaking into other test files' "no streamlit" assertions. |
| #273 | Document the dashboard ↔ DB persistence asymmetry: terraform-deployed dashboard pods received `COSMOS_ENDPOINT` but not `DATABASE_URL`, silently falling back to local SQLite when `enable_postgres = true`. CLAUDE.md note + `deploy/terraform/README.md` known-issue section pointing at the fix path (Helm side already addressed in #271; Terraform Container Apps side queued). |
| #275 | Plant trade-based ML positives (C0020-C0022) + UK APP fraud positives (C0016-C0019) + the `hs_code_baseline` reference table for over/under-invoicing rule joins. New `is_null` SQL filter operator (with strict bool guard against YAML-quoting accidents) so `phantom_shipping`'s `invoice_id: { is_null: true }` filter compiles correctly. |
| #276 | Plug cross-spec contamination from C0012-C0019 planted positives: at certain seeds the noise loop's 4-week background activity pushed those customers' `unusual_volume_spike` baseline_avg over the 5× ratio threshold, leaking false positives into uk_bank, canadian_schedule_i_bank, canadian_bank, and community_bank. Same `txns = [t for t in txns if t["customer_id"] not in <ids>]` guard pattern that PR #275 used for C0020-C0022, now widened to C0012-C0019. |
| #277 | Align C0012/C0013 RTP plant timestamps with the rule windows: `aggregation_window` uses a sliding `[as_of - parse_window, as_of)` (verified at `src/aml_framework/generators/sql.py:154-163`); the prior C0012 plant at `as_of - timedelta(days=1, hours=1)` was 25h back — 1h outside `first_use_payee_large_amount_rtp`'s 24h window — and C0013's burst at `-1d -14h` was 38h outside `velocity_spike_on_receive_rtp`'s 1h window. Two new window-pinning regression tests catch any future drift. |
| #278 | `.gitignore` additions for `terraform.tfstate*`, `deploy/terraform/*.tfplan`, `_temp/`, `/aml_open_framework/` (embedded git-repo experiment), `uv.lock` — files accumulating untracked across recent rounds that risk an absent-minded `git add -A` polluting a future commit. |
| #279 | Populate `counterparty_id` in the synthetic txn data — declared nullable in `us_rtp_fednow`'s `data_contract` but never emitted by `_make_txn`. Three rules use it: `unusual_send_hour_for_customer_rtp` SELECTs it; `first_use_payee_large_amount_rtp` and `ramp_up_then_drain_rtp` `GROUP BY (customer_id, counterparty_id)`. Without real values, the latter two collapsed every txn into a single `(customer, NULL)` group. Also re-anchored C0012's plant hour to a guaranteed-outside-typical-window value regardless of as_of, so `unusual_send_hour_for_customer_rtp` fires under default `aml run` invocations (was firing only when as_of was at midnight). |
| #280 | (bundled into #279 via stacked-PR cascade) Plant C0023 ("Ramp Source LLC") with 4 small RTP outbounds totaling $1,550 to `CP-RAMP-2026-001` for `ramp_up_then_drain_rtp` coverage. Intentional cross-rule firing: `cyber_enabled_fraud`'s broader `ramp_up_then_drain` rule is a strict superset, so this same plant fires it too — net coverage gain on that spec. |

**Result**: us_rtp_fednow's within-spec coverage on planted customers grew from 0/5 to 4/5 (still needs a customer-contract `device_id` linking column to fire `mule_receiver_fan_out_rtp`); trade_based_ml fires 3/5 of its rules end-to-end on the plants (over_invoicing, phantom_shipping, multiple_invoicing); uk_app_fraud fires 4/4. Cross-spec leak guards at C0012-C0022 stop the noise from those plants nudging unrelated specs' all-txn rules. Tests grew 2,084 → 2,168.

**Out of scope (queued):** `mule_receiver_fan_out_rtp` plant (needs `phone`/`email`/`device_id` linking column on the `customer` contract); `unusual_send_hour_for_customer_rtp` cleanup of the `t.counterparty_id` SELECT now that the column is populated (not strictly needed but tidies the SQL).

### Round 17.5 — Live Azure landing-zone deploy (3 PRs, 2026-05-11)

Goal: prove the Round 16 Phase A scaffolding works end-to-end against the user's actual Azure tenant. First live `terraform apply` surfaced three runtime issues no unit test had caught — each shipped as a focused fix PR.

| PR | Workstream |
|---|---|
| #282 | wire `DATABASE_URL` into the dashboard Container App. Helm was fixed in #271; Terraform-deployed dashboard pods still injected only `COSMOS_ENDPOINT`, so on the Postgres path the dashboard silently fell back to local SQLite. New `local.postgres_database_url` hoisted so the value can't drift between API and dashboard. Test asserts both Container App blocks read the same local. |
| #283 | fetch Entra-ID token for Postgres on Azure deploys. The Terraform-generated DSN included `authentication=azure_ad` which psycopg2's DSN parser rejects. `_get_pg_conn()` now detects the marker, strips it via proper URL parsing (not regex), mints a token via `DefaultAzureCredential().get_token("https://ossrdbms-aad.database.windows.net/.default")`, and passes it as `password=` to psycopg2. Five tests pin the strip behavior across marker-position variants + userinfo false-positive. |
| #284 | set `AZURE_CLIENT_ID` on both Container Apps + use AD-admin `principal_name` (not object_id) as Postgres user. With UAMI auth, `DefaultAzureCredential` needs `AZURE_CLIENT_ID` set to know which UAMI to pick. Then Postgres validates AD admins by `principal_name`, not by object_id, so the DSN's user component was wrong. Hoisted to `local.postgres_admin_principal_name` shared by the AD admin resource AND the DSN — test asserts both read the same local. |

**Result**: live deploy at https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io with `/api/v1/health` returning `{"status":"ok","version":"0.1.0"}`. Dashboard healthy at the matching domain. Both pods read/write Postgres `psql-aml-dev-2lusik` via UAMI Entra-ID auth. ~$33/mo idle. Tests grew 2,168 → 2,178.

### Round 18 — Plant fan-out + Azure Phase B differentiation (6 PRs, 2026-05-12)

Goal: close Round 17's `mule_receiver_fan_out_rtp` coverage gap (4/5 → 5/5) and ship the three Azure-shop integrations Round 16 Phase B queued (Azure OpenAI assistant, Sentinel SIEM connector, Purview lineage push).

| PR | Workstream |
|---|---|
| #285 | Pin `counterparty_id` as evidence column on `unusual_send_hour_for_customer_rtp`. Adds inline comment on the rule + fast SQL-string test + heavier engine-run test that asserts the alert payload carries a non-empty counterparty_id. Regression-safe after #279. |
| #286 | Plant 4-mule `device_id` cluster (C0024-C0027) sharing `DEV-MULE-2026-001`. Adds `device_id` (pii: true) to the us_rtp_fednow customer contract + `_customer_row()`. Network_pattern rule `mule_receiver_fan_out_rtp` now fires 4 alerts (one per mule). Intentional cross-spec firings on `cyber_enabled_fraud.pig_butchering_payout_fan` + `crypto_vasp.nested_wallet_ring` — same pattern as #280's C0023 coverage extension. Single-gate guard at `n_customers >= 28`. |
| #287 | Azure OpenAI as 4th GenAI assistant backend. Mirrors the existing `openai.py` Chat Completions shape but routes to per-deployment Azure endpoints. Two auth paths: api-key (header: `api-key`) or Entra-ID bearer token at scope `https://cognitiveservices.azure.com/.default`. Endpoint/deployment/key resolved via SecretsProvider (Key Vault on the deployed Container App). 8 tests cover both auth paths + actionable-error path for unmintable AAD tokens. |
| #288 | Sentinel SIEM connector — active push complement to the existing CEF-export `integrations/siem.py`. POSTs structured AML decision events to the platform Log Analytics workspace via the v1 Data Collector API at `<workspace>.ods.opinsights.azure.com/api/logs`. Shared-key HMAC-SHA256 auth (v1 API doesn't accept Bearer tokens; Logs Ingestion API migration deferred to Round 19). Opt-in via `AZURE_SENTINEL_WORKSPACE_ID`. Module docstring + in-code NOTE explain the deferred audit-ledger emit-hook wiring. |
| #289 | Purview lineage push via Atlas REST API. Maps `walk_lineage()` chains to Atlas entity dicts: `Process(rule:<id>)` with `inputs` (source DataSets) and `outputs` (case DataSet). `qualifiedName` uses a stable `aml://<spec>/<part>/...` scheme so re-pushes update rather than duplicate. `ruleVersion` + `specContentHash` stamped on Process attributes so auditors see which spec snapshot drove each case. Auth via DefaultAzureCredential at scope `https://purview.azure.net/.default`. Opt-in via `PURVIEW_ENDPOINT`. 7 tests cover entity-builder shape, qualifiedName stability, sparse-chain handling. |

**Result**: us_rtp_fednow within-spec coverage goes 4/5 → **5/5**. Azure-shop integration surface adds three connectors (assistant, SIEM, governance lineage) all gated by env vars so non-Azure deployments aren't affected. Tests grew 2,178 → 2,187.

**Deferred to Round 19** (originally scoped in plan but not executed):
- Spec-specific synthetic noise patterns for uk_app_fraud / trade_based_ml / us_rtp_fednow (PR 18.3) — medium-scope refactor; current noise loop works.
- Performance baseline + locust harness (PR 18.7) — infra work.
- `python_ref` matched-row lineage hook (PR 18.8) — opt-in `_inspect_context()` contract.
- PII masking policy layer for audit ledger (PR 18.9) — cross-cutting feature.
- Engine backend abstraction (PR 18.10) — multi-week scope (Snowflake/BigQuery compile targets).
- `aml generate-dbt` (PR 18.11) — dbt-model emit command.
- Audit-ledger emit hooks for the Sentinel + Purview connectors — load-bearing engine change; the surfaces shipped without callers so the wiring can be reviewed in isolation. Future integrators must wrap calls in `try/except` and log-and-continue.
- Logs Ingestion API (DCE/DCR) migration for Sentinel — unlocks Entra-ID auth on the SIEM push but requires terraform-preprovisioned Data Collection Endpoint + Rule.

### Round 19 — GenAI UX polish + CI streamlining (3 PRs, 2026-05-13 → 2026-05-14)

Goal: fix the live-site regression where per-section AI explanations rendered above the page hero (or never resolved on first paint), and stop paying the ~12-min Playwright e2e cost on every PR push.

| PR | Workstream |
|---|---|
| #306 | Revert PR #304's async `ThreadPoolExecutor` dispatch back to synchronous `assistant.reply()` inside `st.spinner()`. The async model returned in ~5 ms but the reply never surfaced without an interaction-driven rerun — operators saw a permanent spinner. A 1-sec polling fragment had fixed visibility but killed the Playwright suite via networkidle starvation (100/100 → 15/100). Synchronous baseline trades ~2-3 sec first-paint per unique section for actually-visible AI output. Kept: process-global `_PROCESS_CACHE` (cross-session), `_resolve_model` complexity-tier routing, audit hook. Module dropped from 445 lines → 320 with 100% test coverage. |
| #307 | Gate `e2e-dashboard` to push-to-main only via `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. PR feedback drops ~15 min → ~5 min. Local `make pre-push` still runs e2e — CLAUDE.md "PR/CI is the last gate, not a feedback loop" makes the local hook the canonical contract. Main-push e2e remains as post-merge safety net; Azure auto-deploy gates on main green so a broken e2e blocks deploy rather than reaching live. Branch protection on main updated via `gh api` to drop `e2e-dashboard` from required status checks (without that, every future PR would be permanently waiting on the now-skipped required check). |
| #308 | Move page-level `section_explainer(...)` below each page's hero/intro on 32 dashboard pages. Streamlit renders in script order — the explainer was firing before `page_header()` / dna-hero / `show_audience_context()` on most pages. AST-respecting script relocated the call to right after the last intro marker; stable `section_id` preserved so the cross-session `_PROCESS_CACHE` + audit trail stay continuous. 3 pages (`1_Executive_Dashboard`, `3_Alert_Queue`, `5_Rule_Performance`) already called section_explainer deep-inline after specific charts and were untouched. |

**Azure redeploy**: two `az acr build` + `az containerapp update` cycles ran during the round (after #306 merge, again after #308 merge). Image tags use `+` → `-` sanitization since Docker tags reject PEP440 local-version markers. Dashboard Container App's `OLLAMA_API_KEY` secret + env-var binding added (was missing — explained the live site's template-backend placeholder text in the user's screenshot evidence). Both apps now live on `aml-framework:0.1.1.dev5-g83045d6de` at https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io/api/v1/health and the matching dashboard host.

**Result**: AI explanations render below the hero on every page, fire synchronously on first paint with a visible spinner, and cache cross-session so revisits are <1 ms. PR feedback time cut by ~60% with the same coverage guarantee. Tests grew 2,187 → 2,272 (+85, mostly section_explainer test simplification + the sync-flow test rewrite).

### Round 20 — GenAI advisor reliability + visibility + FAB entry point (4 PRs, 2026-05-14)

Goal: chase down a user-visible bug ("each page has AI summary with low confidence, not sure which model was used") and the screenshot evidence that the AI Explanation block on every live page rendered canned template text despite `AML_AI_BACKEND=ollama` on the Container App. Surface the real failure, route the sidebar advisor through the deep model tier, and add a floating-action-button entry point so the chat is reachable without scrolling past Streamlit's 32-page nav.

| PR | Workstream |
|---|---|
| #310 | Bottom-padding regression on short empty-state pages. `My Queue` ended flush against the viewport; PR #305's 4rem bump wasn't enough. `padding-bottom` to 8rem, `min-height: calc(100vh - var(--dna-topbar-h))` so short pages fill the viewport. CSS-only in `dashboard/components.py`. Tagged `v0.1.3`. |
| #311 | Surface real LLM backend errors. `_call_backend` in `section_explainer` AND `_handle_ai_submission` in the sidebar advisor both silently caught every exception and returned a TemplateBackend reply — auth / model / network failures on ollama or openai were invisible. Replace silent fallback with visible `st.error(...)` banners naming backend, model, and exception. Side-effect bug: `TemplateBackend.__init__` didn't accept `model=` kwarg (every section_explainer call passed one because `_resolve_model` always returns a string); added `model` kwarg that the template ignores. Codex review caught a regression — `_resolve_model` reads `AML_OLLAMA_MODEL_*` env vars whose values name ollama model strings, so forwarding `model=` to OpenAI would 400 and Azure OpenAI rejects the kwarg. Gated on `backend_name == "ollama"`. Also clears stale `ai_transcript[page]` on submission failure so a prior reply doesn't render below the new error banner. Tagged `v0.1.4`. |
| #312 | Sidebar advisor wired through the deep model tier. `_handle_ai_submission` was calling `get_assistant(backend_name)` with NO `model=`, so OllamaBackend fell back to `AML_OLLAMA_MODEL` (set to `gpt-oss:120b` on the live Container App, overriding `AML_OLLAMA_MODEL_DEEP=deepseek-v4:pro`). Thread `_resolve_model("deep")` for ollama backends only. Surface the resolved model in the sidebar pill (`AI Assistant · ollama · deepseek-v4:pro`) and as a chip next to the confidence badge in `_render_assistant_reply`. Page 29 (AI Assistant) replaced its single `Model:` row with three (fast tier inline / deep tier sidebar / legacy fallback if set). HTML-escape both the backend and model labels via `html.escape` before interpolating into `unsafe_allow_html=True` markdown — operator-controlled env vars could otherwise inject markup. Tagged `v0.1.5`. |
| #313 | Floating-action-button entry point. User screenshot showed the sidebar `ai_panel` is invisible: Streamlit's `st.navigation()` widget claims the top of the sidebar with the 32-page grouped nav and the ai_panel renders below — operators have to scroll a full viewport down to reach it. Added `ai_panel_fab(page)`: `st.container(key="ai_fab_container")` produces a `<div class="st-key-ai_fab_container">` whose injected CSS pins it `position: fixed; bottom: 1.5rem; right: 1.5rem`; the popover button inside is styled as a rounded blue pill with a shadow. `st.popover` (NOT `st.dialog` — dialogs auto-close on the Ask submission rerun, hiding the reply). Widget keys suffixed `_fab_` so the FAB and the existing sidebar advisor can coexist on the same page without duplicate-key collision; both share `ai_transcript[page]` so a reply asked via either surface shows on both. `pyproject.toml` streamlit floor bumped 1.35 → 1.39 because `st.container(key=...)` requires 1.39+ (Codex caught the silent-failure scenario on older allowed installs). Tagged `v0.1.6`. |

**Azure redeploys**: four `az acr build` + `az containerapp update` cycles ran during the round, one per merge — `v0.1.3` (bottom padding), `v0.1.4` (errors visible), `v0.1.5` (sidebar Pro + model UI), `v0.1.6` (FAB). Each tag pushed via `git tag -a` first so `setuptools-scm` produces a clean version on `/api/v1/health`. Both `ca-aml-api-dev` and `ca-aml-dashboard-dev` rolled together each cycle.

**Codex review iterations**: three rounds of `/codex:review --base main` per PR (#311, #312, #313) caught four real blockers before merge — ollama-only model routing, false `openai · deepseek-v4:pro` pill label, streamlit version floor, and the OpenAI pill regression test. Each block was addressed with a follow-up commit and re-reviewed.

**Memory updates**: `feedback_azure_local_deploy_after_ci.md` strengthened to "deploy on green is reflexive, not optional" per user directive — plan mode no longer blocks the post-merge ship. `feedback_auto_merge.md` index entry corrected (it had said "no auto-merge" but the body had been "merge on green" since 2026-05-08).

**Result**: AI is now diagnosable on the live stack — operators see the real ollama error (or success) instead of canned template text. Sidebar replies come from DSv4 Pro with the model attribution visible next to the confidence badge. Floating button gives a one-click entry point regardless of scroll position. Tests grew 2,272 → 2,294 (+22). CLAUDE.md updated: "outline approach inline in 1-2 sentences then implement; do not call exit_plan_mode."

### Round 21 — non-blocking AI + real coverage gate + OS-following dark theme (6 PRs, 2026-05-16 → 2026-05-17)

Goal: make the per-section AI non-blocking (page renders first, the explanation fills in) with visible "thinking" feedback; fix the now-genuinely-enforced 99% coverage gate; and build a real OS-following dark theme after a live screenshot showed the dashboard illegible (dark-navy ink on a dark canvas) in OS dark mode.

| PR | Workstream |
|---|---|
| #316 | ollama model tag hyphen fix — ollama.com tags use `deepseek-v4-flash` / `deepseek-v4-pro` (hyphen), not the colon form. Env vars + code defaults corrected; surfaced a broader lesson (see Memory). Tagged `v0.1.7`. |
| #318 | Non-blocking async `section_explainer`: `ThreadPoolExecutor` dispatch keyed by `(page, section_id, persona, data_hash)`, a `@st.fragment(run_every="1.2s")` poller that promotes resolved futures under a two-phase claim-lock, dispatch-time audit-context snapshot, `st.error` on failure. The Ask button greys to a "Thinking…" spinner state. This is the *async fill* the Round-19 revert (#306) had deferred — done right this time with `domcontentloaded` + a shell-selector e2e wait instead of `networkidle` (which the 1-sec fragment had starved). Five Codex rounds: silent fallback, ollama-only routing, drain race, non-atomic publish, audit-once. |
| #319 | Genuinely raise repo coverage to 99.32%. A pytest-cov quirk that had masked the `--cov-fail-under=99` gate vanished in a runner update, exposing real ≈98.5% coverage. Closed with real tests (no pragma-gaming). Tagged with #318 as `v0.1.8`. |
| #320 | **Dark-theme PR-1 — foundation.** `:root` defines light `--dna-*` vars; `@media (prefers-color-scheme: dark)` redefines every role-bearing var; previously-hardcoded inline colours (KPI value/label, hero tint, topbar) refactored to read the vars so they flip. `.streamlit/config.toml` reduced to `primaryColor` + `font` only (a static bg/text pin can't be scheme-aware — it was the original lock). Codex caught topbar/header/native-metric still hardcoded; fixed. `--dna-card-border` added as a solid dark mid-grey clearing WCAG 1.4.11 3:1 (the translucent `--dna-rule` couldn't on near-black). Tagged `v0.1.9`. |
| #322 | **Dark-theme PR-2 — theme-neutral charts.** Canvas-rendered ECharts can't read the CSS dark theme. The first approach — a client `prefers-color-scheme` bridge that set a query param and reloaded — was **abandoned mid-PR**: Codex showed the reload re-runs the AML engine with a fresh `as_of` (state cached only in `st.session_state`), so windowed rules evaluate over a shifted window and the immutable audit ledger records two divergent runs — a determinism-contract break unacceptable in a compliance tool. Pivoted to theme-neutral: transparent chart background (the CSS-themed card shows through) + a retuned `CATEGORICAL_PALETTE` and `DNA_CHART_*` tokens whose relative luminance sits in a band clearing WCAG 1.4.11 3:1 on **both** the cream and the `#212832` dark card; the opaque tooltip is self-contained. Real WCAG luminance maths in the unit tests mirror the e2e dark test. Six Codex rounds (incl. a heatmap-default-ramp bypass via the public wrapper). Tagged `v0.1.10`. |
| #323 | **Dark-theme PR-3 — secondary-chrome sweep.** Routed the deep-link colour, "(no prior runs)" / AI-assistant / citation-count labels, and the sparkline neutral through PR-1's dark-aware tokens. Codex HOLD caught a real trap: functional labels first routed onto `--dna-ink-faint` (PR-1's *intentional* de-emphasis token, 2.33:1 on cream — fails even non-text 3:1), fixed to `--dna-ink-dim` (clears 4.5:1 text on both). Tagged `v0.1.11`. |

**Deliberately deferred** (documented in-code, not silently changed): semantic SEVERITY/RAG/`breached` colours stay a regulator-standard convention (forcing dual-safe would break "breach reads red" and touches DOM badge consumers) — own follow-up; and AG Grid dark theming (`data_grid.py`) — streamlit-aggrid renders in its own iframe so the parent `--dna-*` vars don't cascade in, a separate cross-iframe PR-3b.

**Azure redeploys**: five `git tag -a` + `az acr build` + `az containerapp update` (both `ca-aml-api-dev` + `ca-aml-dashboard-dev`) cycles, `v0.1.7` → `v0.1.11`. The `v0.1.10` build first shipped `0.1.0+local` because `az acr build` was invoked without the `--build-arg APP_VERSION=… GIT_SHA=…` the Dockerfile expects (the image carries no `.git`); rebuilt with the args and rolled by image digest (a same-tag push doesn't force a new Container App revision). Both apps verified live at `/api/v1/health` reporting clean `0.1.11` / `543157a`.

**Doc-scope note**: `CHANGELOG.md` `[Unreleased]` is pre-existing drift-stale — its newest entry is Round 16; Rounds 17–21 are unrecorded there. This is **intentionally not backfilled** in this focused progress-doc update (5 rounds of CHANGELOG history is its own dedicated catch-up); `docs/progress.md` remains the canonical state-of-project snapshot in the interim.

**Result**: page-level AI no longer blocks first paint and shows a thinking state; the 99% gate is real and enforced; the dashboard follows OS dark mode with WCAG-conformant contrast on every primary surface and chart, with two scoped follow-ups tracked in-code. Tests grew 2,294 → 2,357 (+63). Memory added: verify external identifiers empirically; drain the worklog without asking permission; **commit before any Codex review** (the local Codex companion runs destructive `git reset`/`checkout` that discards uncommitted work — this cost one re-apply of a Codex-HOLD fix).

### Round 22 — Data Integration epic (3 PRs, 2026-05-17)

Goal: act on "dig into more features on the Data Integration tab — enable more testing data and channels for each type." Investigation established the determinism trap up front (the synthetic generator seeds RNG once, then a ~400-txn noise loop consumes it sequentially *before* the planted positives), so the user was asked to choose the approach; they picked **additive, determinism-preserving** over a full dataset re-base.

| PR | Workstream |
|---|---|
| #325 | **PR-A — additive rails + typologies (`v0.1.12`).** `_NEW_RAILS = [rtp, crypto, prepaid]` kept OUT of `_CHANNELS` (so the seeded noise loop's `random.choice(_CHANNELS)` draw is byte-identical — no re-base). New plants C0028 (crypto VASP rapid pass-through + prepaid-load structuring) and C0029 (RTP instant-payment burst) appended AFTER the C0022 block using only hardcoded amounts/offsets (zero `random.*`); only 2 free customer slots, so C0028 carries two typologies; a new-rail background block is RNG-free (`tid % N`) and excludes the cross-spec-guarded plant ids. Canonical spec: channel enum extended + 3 new rules (`crypto_vasp_rapid_passthrough` custom_sql, `rtp_instant_payment_burst` + `prepaid_load_structuring` aggregation_window) mirroring existing rule shapes; all citations resolve via the existing `CITATION_URL_MAP` (crypto rule cites the already-mapped FINTRAC LVCTR — no URL invented). Codex HOLD: the crypto rule was looser than its "cash-in → crypto-out" description (no `channel='cash'`, only the crypto leg gated) — fixed to require `channel='cash'` + both legs ≥ $30k. Reproducibility test stayed green (no re-base); test_api rule-count golden 10 → 13. |
| #326 | **PR-B — fixtures + honest cloud local-mock (dev tooling, no deploy).** `data/fixtures.py` + `make fixtures` / `python -m`: deterministic parquet (one file/contract) + duckdb (one table/contract) from `generate_dataset(seed=42, as_of=pinned)` via pyarrow (type-faithful). `data/fixtures/` gitignored — parquet/duckdb aren't byte-deterministic, so committing them would fight the determinism contract; regen is one reproducible command. An EXPLICIT local-mock path for the 8 cloud/warehouse types: the literal `mock`/`mock:<x>` as the conn/bucket arg serves the seeded data via in-memory DuckDB with a loud "LOCAL MOCK (no live credentials)" warning — a real conn string/URI never equals `mock` so production paths are byte-untouched (75 insertions / 0 deletions), and several `# pragma: no cover` infra stubs became really-tested. New `sample_pacs008_rtp_crypto.xml` ISO-20022 sample for the PR-A typology. Codex MERGE + 2 non-blocking nits fixed test-only (per-test duckdb skip-guard so the pure sentinel-safety tests run on lean CI; semantic ISO assertions). |
| #327 | **PR-C — richer Data Integration UI (`v0.1.13`).** Two additive, self-contained sections on `pages/30_Data_Integration.py` (104 insertions / 0 deletions): "Demonstrable test data per source type" (every connector + how to get demo data locally — live-checks CSV/fixtures presence, points cloud types at `--data-dir mock`) and "Volume by payment channel" (groups the wired source's txns by rail → the theme-neutral `bar_chart` from dark PR-2, so the PR-A rails are visible here, with an `empty_state` fallback). 7 file-text source guards; render covered by the existing Data Integration e2e. |

**Azure redeploys**: two cycles — `v0.1.12` (#325) and `v0.1.13` (#327), both apps rolled by image digest with the correct `--build-arg APP_VERSION/GIT_SHA` from the start (the Round-21 `v0.1.10` lesson). PR-B shipped no deploy: the live dashboard uses synthetic/CSV, so the fixtures + opt-in mock are dev/demo tooling with no live behavioural change (same precedent as the docs PRs). Both apps verified live at `/api/v1/health` reporting clean `0.1.13` / `5c3e08c`.

**Result**: every one of the 9 source types is now demonstrable locally with zero live credentials; modern rails (rtp/crypto/prepaid) flow through the deterministic synthetic data, trip dedicated rules, and are visible on the Data Integration page — all without re-basing the reference dataset (every pre-existing alert-count/hash golden untouched). Tests grew 2,357 → 2,400 (+43). The CHANGELOG `[Unreleased]` drift (stale at Round 16) remains a tracked, deliberately-deferred catch-up — `docs/progress.md` is the canonical snapshot in the interim.

---

## What the Framework Does Today

### For the policy author (CCO / MLRO)
- Authors a versioned `aml.yaml` — every rule cites a specific regulation
- Two-layer validation (JSON Schema + Pydantic cross-references)
- Reusable rule snippet library (`spec/library/`) for ISO 20022 typologies
- Reviewable diff between spec versions (`aml diff`)

### For the data engineer
- Generates SQL, DAG stubs, and control matrix from spec
- 8 supported data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery
- Native ISO 20022 ingestion (pacs.008/009/pain.001/pacs.004)
- Schema validation at load time

### For the analyst (L1/L2)
- 32-page web dashboard with persona-filtered navigation
- Row-click drill-through on every triage table (no more selectbox-below-table)
- Investigation-level review (not just alerts)
- Per-case live SLA + escalation recommendations
- Network-pattern explainability with Mermaid diagrams
- One-click STR submission bundle
- GenAI co-pilot in the sidebar — auto-scoped to current page + run, with citation chips linking back into the dashboard

### For the auditor / regulator
- Append-only decisions ledger with SHA-256 hash chain
- Reproducible runs (same spec + data + seed → identical hashes)
- Regulator-ready evidence ZIP (`aml export`)
- goAML 5.0.2 XML and AMLA RTS JSON exports
- **End-to-end lineage walk-back** (Round 12 + 13): paste any `case_id` → 7-link chain (source file → contract → DuckDB table → rule SQL → matched source rowids → alert → case → STR), each link hash-stamped + reproducible, downloadable as JSON. Surfaces on Audit & Evidence, Case Investigation "Why this fired" panel, the dedicated Lineage Explorer page (#32), AND on Alert Queue / My Queue / Investigations / Customer 360 / Network Explorer / Sanctions Screening / Rule Performance / Run History / Tuning Lab / Today / Executive Dashboard / AI Assistant / Analyst Review Queue inline columns + breadcrumbs (Round 13). STR bundle / FINTRAC audit pack / FinCEN effectiveness pack carry the chain in their manifests. CLI: `aml lineage <case_id>` + `aml verify-decisions`. API: `GET /api/v1/runs/{run_id}/cases/{case_id}/lineage`.

### For the ML modeler
- `python_ref` rule type with security gate (callables restricted to `aml_framework.models.*`)
- MRM bundle generator (SR 26-2 / OCC Bulletin 2026-13 dossiers)
- Tuning Lab — threshold sweep with shadow diff + precision/recall
- Effectiveness Evidence Pack (FinCEN April 2026 NPRM artifact)

### For the operations team
- Multi-tenant dashboard (single process, multiple programs)
- Mobile-responsive layout
- REST API with JWT/OIDC auth, rate limiting, run persistence
- Integrations: Jira, Slack/Teams, SIEM/CEF
- Docker + Helm chart for K8s deployment

---

## Shipped Capabilities by Regulatory Regime

| Regulator / regime | What's covered |
|---|---|
| **FinCEN BSA** (US) | 6-pillar mapping including the April 2026 proposed 6th pillar; SAR/CTR exports; investigation-aggregation per the 2024 effectiveness rule |
| **FinCEN April 2026 NPRM** | Effectiveness Evidence Pack generator (`aml effectiveness-pack`) |
| **OFAC** | Fuzzy + exact name screening; SDN list refresh from upstream XML |
| **FINTRAC + OSFI** (CA) | PCMLTFA section-level citations; STR/LCTR/EFTR; OSFI B-8 alignment; TD case-study patterns spec |
| **AMLD6 + EBA** (EU) | Article-level citations; AMLA RTS JSON draft (effective July 2026); 5-year retention |
| **FCA + POCA + PSR** (UK) | UK SAR via NCA; PSR APP-fraud reimbursement signals (return-reason mining); FCA Mar 2026 SAR-backlog response |
| **FATF** | R.16 Travel Rule validator; R.15-16 crypto adaptations (`crypto_vasp` spec); Feb 2026 Cyber-Enabled Fraud typologies |
| **Wolfsberg** | Feb 2026 correspondent-banking gaps (pain.001 ingestion, submission-ready STR packages) |
| **SR 26-2 / OCC 2026-13** | MRM bundle generator for python_ref models |

---

## Test Coverage

```
test_engine.py                  108  Engine, audit ledger, hash chain, all 5 rule types
test_iso20022.py                 34  pacs.008/009 parsing
test_pain001.py                  29  Corporate batch ingestion
test_pacs004.py                  36  Payment-return ingestion + library
test_iso20022_purpose_codes.py   16  Purpose-code library + planted positive
test_travel_rule.py              29  FATF R.16 validator
test_cases_aggregator.py         34  Investigation grouping (3 strategies)
test_cases_sla.py                25  SLA classification + escalation + backlog
test_cases_str_bundle.py         23  Per-investigation ZIP determinism
test_dashboard_workflows.py      15  Audience map + executive scale + page registration
test_dashboard_tenants.py        26  Multi-tenant config validation
test_dashboard_mobile_css.py     10  Mobile responsive overlay
test_e2e_dashboard.py            30  Playwright — every page renders
test_e2e_dashboard_mobile.py      9  Mobile viewports (375/414/768)
test_dashboard_investigations    9   Investigations page wiring
test_docs_links.py               19  Link rot prevention
test_api.py                      54  FastAPI auth, runs, validation, rate limiting
test_data_sources.py             37  All 8 source types
test_generators.py               26  All export formats
test_metrics.py                  30  Metric evaluation + RAG + audience
test_integrations.py             24  Jira, Slack/Teams, SIEM/CEF
test_spec.py                     28  Spec validation + EU/UK runs + AMLD6 alignment
test_performance.py               2  10k+ row engine throughput
… plus 19 other test files       … 
```

Total (post Round 7 + dashboard plan): 1,161 tests passing, 43 test files.

Dashboard-plan tests added (2026-04-27 → 2026-04-28):
```
test_dashboard_components_helpers.py   21  Phase A — 6 helpers + namespace tests
test_dashboard_sla_integration.py      18  Phase B-1 — SLA on 3 pages
test_dashboard_outcomes_panel.py       13  Phase B-2 — funnel + regwatch
test_dashboard_audit_pack_button.py    11  Phase B-3 — FINTRAC + VoP panel
test_dashboard_drill_downs.py          17  Phase C — deep-link wiring
test_dashboard_design_consistency.py   10  Phase E — page_header + empty_state + resolvers
```

---

## What's NOT in the Framework (by design)

These are documented "won't ship" decisions, not gaps:

- **Generative AI rule-*authoring*** (English → YAML rule). Would destroy the "human-readable spec written by a human" moat that's the framework's whole differentiation. *The dashboard's GenAI assistant (PR-K) is read-only — it answers questions about the spec + run, it does not propose rule edits. Rules stay human-authored.*
- **Native graph DB backend** (Neo4j / TigerGraph). DuckDB-with-graph-views is fast enough for FI-scale datasets, and "one binary, one DuckDB file" deployability is the moat.
- **Alert-scoring ML model in-tree**. Would erode the deterministic re-run guarantee that the MRM bundle (PR #53) builds on. We document the `python_ref` seam; institutions ship their own model.

See `memory/project_round5to9_plan.md` (private) for the full "three new traps" rationale.

---

## Open Items

- Issue #66 — closed 2026-04-27 (PR #70 mobile-responsive)
- Issue #68 — closed 2026-04-30 (PR #159 / PR-J). Docs-sweep half: only `dashboard-tour.md` had drifted; fixed + added `test_dashboard_tour_coverage.py` so future drift fails CI immediately rather than waiting 30 days for a manual sweep ticket. Mobile half: confirmed already satisfied by `#66` / PR #70.
- No other tracked issues open as of this snapshot

## Round 8 / 9 — Remaining Planned Work

The deep-research-agent's 5-round plan (in `memory/project_round5to9_plan.md`) is now substantially shipped. Round 10 (data-layer hardening) closed the cross-border information-sharing item (9.5) by shipping the spec syntax + CLI + dashboard surface (PR-DATA-10a/b). Status as of 2026-05-02:

| Round | Item | Estimate | Status |
|---|---|---|---|
| 8.1 | UK APP-fraud spec | 3d | shipped — Round 7 PR #76 |
| 8.2 | RTP/FedNow push-fraud detector pack | 3d | **shipped** — `examples/us_rtp_fednow/aml.yaml` |
| 8.3 | Regulatory-change diff watcher (regwatch) | 3d | shipped — Round 7 PR #74 |
| 8.4 | Fraud-AML unified case linkage | 3d | **shipped** — `cases/linkage.py` (cyber_enabled_fraud spec is the only consumer; a cross-spec example would deepen this) |
| 8.5 | Beneficial Ownership (BOI) workflow page | 3d | **shipped** — `dashboard/pages/25_BOI_Workflow.py` |
| 9.1 | FINTRAC pre-examination audit pack | 3d | shipped — Round 7 PR #78 |
| 9.2 | Open Compliance API draft | 3d | **shipped** — `api/openapi-compliance.yaml` |
| 9.3 | Guided demo CLI (`aml demo`) | 3d | **shipped** — `cli.py` |
| 9.4 | Synthetic data quality upgrade for new specs | 3d | partial |
| 9.5 | Cross-border information-sharing sandbox (FATF R.18) | 5d | **shipped** — `compliance/sandbox.py` |

The only Round-8/9 item with meaningful work left is 9.4 (~3 engineer-days) — a synthetic-data quality pass for the newer specs (`us_rtp_fednow`, `uk_app_fraud`, `trade_based_ml`) so each ships with its own planted-positives demo run, not just the inherited `community_bank` data. 8.4 is flagged "shipped but partial" because the unified case-linkage code is in but only `cyber_enabled_fraud` exercises it; a fraud↔AML cross-spec example would be the next deepening step.

---

## Documentation Index

Every doc has a single-line "use when" hook in [`README.md`](../README.md). The full set:

- `README.md` — hub-style entry point with documentation map
- `docs/getting-started.md` — 15-min onboarding path
- `docs/architecture.md` — reference design
- `docs/dashboard-tour.md` — all 32 pages organized by workflow (drift-protected by `test_dashboard_tour_coverage.py`)
- `docs/jurisdictions.md` — US / CA / EU / UK / crypto / cyber-fraud specs
- `docs/personas.md` — role-based workflows
- `docs/spec-reference.md` — field-by-field `aml.yaml` guide
- `docs/api-reference.md` — REST endpoint catalogue
- `docs/audit-evidence.md` — evidence bundle specification
- `docs/metrics-framework.md` — metric types, RAG, audience routing
- `docs/regulator-mapping.md` — coverage matrix
- `docs/deployment.md` — Docker + Helm
- `docs/case-studies/` — TD 2024 enforcement walkthrough
- `docs/progress.md` — this file
