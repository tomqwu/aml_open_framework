"""Compile a spec rule into deterministic, auditable SQL.

Only `aggregation_window` and `custom_sql` logic types are executable in the
reference slice. `list_match` and `python_ref` compile to SQL stubs with a
clear marker and are exercised by tests but not run end-to-end.

All compiled SQL is written to the evidence bundle so auditors can read the
exact query that produced each alert.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from aml_framework.spec.models import AggregationWindowLogic, CustomSQLLogic, Rule

# Having keys → SQL aggregate expressions.
_HAVING_AGGREGATES: dict[str, str] = {
    "count": "COUNT(*)",
    "sum_amount": "SUM(amount)",
    "max_amount": "MAX(amount)",
    "min_amount": "MIN(amount)",
    "avg_amount": "AVG(amount)",
}


def parse_window(window: str) -> timedelta:
    """'30d' → timedelta(days=30). Suffix: s, m, h, d."""
    unit = window[-1]
    n = int(window[:-1])
    if unit == "s":
        return timedelta(seconds=n)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    raise ValueError(f"unsupported window unit in '{window}'")


def _sql_literal(v: Any) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return "NULL"
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _compile_filter(filter_dict: dict[str, Any] | None) -> list[str]:
    """Filter DSL → list of SQL predicates (AND-joined by caller)."""
    if not filter_dict:
        return []

    preds: list[str] = []
    for field, cond in filter_dict.items():
        if not isinstance(cond, dict):
            preds.append(f"{field} = {_sql_literal(cond)}")
            continue

        for op, arg in cond.items():
            if op == "in":
                values = ", ".join(_sql_literal(v) for v in arg)
                preds.append(f"{field} IN ({values})")
            elif op == "between":
                lo, hi = arg
                preds.append(f"{field} BETWEEN {_sql_literal(lo)} AND {_sql_literal(hi)}")
            elif op == "gte":
                preds.append(f"{field} >= {_sql_literal(arg)}")
            elif op == "lte":
                preds.append(f"{field} <= {_sql_literal(arg)}")
            elif op == "gt":
                preds.append(f"{field} > {_sql_literal(arg)}")
            elif op == "lt":
                preds.append(f"{field} < {_sql_literal(arg)}")
            elif op == "eq":
                preds.append(f"{field} = {_sql_literal(arg)}")
            elif op == "ne":
                preds.append(f"{field} <> {_sql_literal(arg)}")
            else:
                raise ValueError(f"unsupported filter operator '{op}' on field '{field}'")
    return preds


def _compile_having(having: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Having DSL → (select_exprs, predicates).

    Select exprs expose the aggregate value with the same name (e.g.
    SUM(amount) AS sum_amount). Predicates reference the column *name* so
    they can be used in a WHERE against the aggregated CTE.
    """
    select_exprs: list[str] = []
    preds: list[str] = []
    for metric, cond in having.items():
        agg = _HAVING_AGGREGATES.get(metric)
        if agg is None:
            raise ValueError(f"unsupported having metric '{metric}'")
        select_exprs.append(f"{agg} AS {metric}")
        if not isinstance(cond, dict):
            preds.append(f"{metric} = {_sql_literal(cond)}")
            continue
        for op, arg in cond.items():
            sym = {"gte": ">=", "lte": "<=", "gt": ">", "lt": "<", "eq": "=", "ne": "<>"}.get(op)
            if sym is None:
                raise ValueError(f"unsupported having operator '{op}' on '{metric}'")
            preds.append(f"{metric} {sym} {_sql_literal(arg)}")
    return select_exprs, preds


def compile_rule_sql(rule: Rule, as_of: datetime, source_table: str) -> str:
    """Return auditable SQL for the rule. Literals inlined, no parameters.

    `source_table` is the physical table the contract resolves to in the
    runtime warehouse (e.g. 'txn' in DuckDB, 'raw.transactions' in prod).
    """
    logic = rule.logic

    if isinstance(logic, CustomSQLLogic):
        header = _rule_header(rule, as_of)
        return f"{header}\n{logic.sql.strip()}\n"

    if not isinstance(logic, AggregationWindowLogic):
        raise NotImplementedError(
            f"rule '{rule.id}': logic type '{logic.type}' is not executable "
            f"in the reference engine. Use custom_sql or python_ref."
        )

    window_delta = parse_window(logic.window)
    window_start = as_of - window_delta

    filter_preds = _compile_filter(logic.filter)
    filter_preds.extend([
        f"booked_at >= TIMESTAMP {_sql_literal(window_start.isoformat(sep=' '))}",
        f"booked_at <  TIMESTAMP {_sql_literal(as_of.isoformat(sep=' '))}",
    ])
    where_clause = "\n    AND ".join(filter_preds)

    group_by = ", ".join(logic.group_by)
    having_selects, having_preds = _compile_having(logic.having)
    having_clause = " AND ".join(having_preds)

    group_select = ", ".join(logic.group_by)
    agg_selects = ",\n    ".join(having_selects)

    header = _rule_header(rule, as_of)
    return f"""{header}
WITH filtered AS (
    SELECT *
    FROM {source_table}
    WHERE {where_clause}
),
agg AS (
    SELECT
        {group_select},
        {agg_selects},
        MIN(booked_at) AS window_start,
        MAX(booked_at) AS window_end
    FROM filtered
    GROUP BY {group_by}
)
SELECT
    {_sql_literal(rule.id)} AS rule_id,
    {group_select},
    {', '.join(m for m in logic.having.keys())},
    window_start,
    window_end
FROM agg
WHERE {having_clause}
ORDER BY {group_by}
"""


def _rule_header(rule: Rule, as_of: datetime) -> str:
    refs = "; ".join(f"{r.citation}" for r in rule.regulation_refs)
    return (
        f"-- rule_id:       {rule.id}\n"
        f"-- rule_name:     {rule.name}\n"
        f"-- severity:      {rule.severity}\n"
        f"-- regulations:   {refs}\n"
        f"-- as_of:         {as_of.isoformat()}"
    )
