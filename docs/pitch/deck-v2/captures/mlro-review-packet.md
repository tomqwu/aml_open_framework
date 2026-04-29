# MLRO Review Packet · `structuring_cash_deposits`

**Proposer:** Aisha N. (Senior Analyst, FCC)
**Generated:** 2026-04-29 02:23 UTC
**Spec:** `examples/canadian_schedule_i_bank/aml.yaml`

## 1. Rationale

Lower sum_amount threshold from $20k to $15k. Internal precision audit (Q1 2026) flagged 3 suspicious patterns in the 15-20k band that escaped detection. Backtest shows +14% recall, -2% precision.

## 2. Expected impact

+12 alerts/month, +1 likely STR

## 3. Diff (current → proposed)

```diff
--- current
+++ proposed
@@ -1,36 +1,21 @@
-  - id: structuring_cash_deposits
-    name: Cash structuring — deposits below LCTR $10,000 threshold
-    severity: high
-    regulation_refs:
-      - citation: "PCMLTFA s.11.1"
-        description: "Structuring offence — splitting transactions to avoid reporting."
-      - citation: "PCMLTFR s.7(1)"
-        description: "LCTR filing obligation for cash transactions of $10,000+ CAD."
-    logic:
-      type: aggregation_window
-      source: txn
-      filter:
-        channel: cash
-        direction: in
-        amount: { between: [5000, 9999] }
-      group_by: [customer_id]
-      window: 30d
-      having:
-        count:      { gte: 3 }
-        sum_amount: { gte: 20000 }
-    escalate_to: l1_aml_analyst
-    evidence:
-      - all_matching_transactions
-      - customer_kyc_profile
-      - prior_alerts_90d
-    tags: [structuring, cash, lctr]
-    # Sweep grid for `aml tune --rule structuring_cash_deposits`. Pairs
-    # of count + sum_amount thresholds an MLRO might consider before
-    # changing production thresholds. The tuner shows alert-count
-    # delta vs the production setting (count≥3, sum_amount≥20000).
-    tuning_grid:
-      logic.having.count:      [{gte: 2}, {gte: 3}, {gte: 4}, {gte: 5}]
-      logic.having.sum_amount: [{gte: 15000}, {gte: 20000}, {gte: 30000}]
-
-  # --- RAPID PASS-THROUGH: cash-in then e-transfer-out within 48h ---
-  # TD failure: pass-through typology across $470M+ was undetected.
+- id: structuring_cash_deposits
+  name: Cash structuring — deposits below LCTR $10,000 threshold
+  severity: high
+  regulation_refs:
+    - citation: "PCMLTFA s.11.1"
+      description: "Structuring offence — splitting transactions to avoid reporting."
+    - citation: "PCMLTFR s.7(1)"
+      description: "LCTR filing obligation for cash transactions of $10,000+ CAD."
+  logic:
+    type: aggregation_window
+    source: txn
+    filter:
+      channel: cash
+      direction: in
+      amount: { between: [5000, 9999] }
+    group_by: [customer_id]
+    window: 30d
+    having:
+      count:      { gte: 3 }
+      sum_amount: { gte: 15000 }
+  escalate_to: l1_aml_analyst
```

## 4. Alert delta

_(no delta computed — re-run with `--with-impact` to attach)_

## 5. Regulation citations (preserved from current rule)

- PCMLTFA s.11.1
- PCMLTFR s.7(1)

## 6. 2LoD sign-off

| Role | Name | Date | Decision | Notes |
|---|---|---|---|---|
| **Proposer (1LoD)** | Aisha N. (Senior Analyst, FCC) | 2026-04-29 | _Submitted_ | _(rationale above)_ |
| **2LoD Reviewer** | _(fill in)_ | _(fill in)_ | _( ) Approve · ( ) Reject · ( ) Defer_ | _(fill in)_ |
| **MLRO Sign-off** | _(fill in)_ | _(fill in)_ | _( ) Approve · ( ) Reject_ | _(fill in)_ |

---

_This packet is the audit-trail artifact for the spec change. Save it
in the PR description; the spec PR + this packet together answer the
auditor's "who decided?" question 18 months later._
