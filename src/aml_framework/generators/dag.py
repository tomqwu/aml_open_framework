"""Generate an Airflow DAG stub from the spec.

The stub is not meant to run as-is — it gives a data engineer the correct
task structure (one task per rule, dependencies in alert-then-report order)
with TODOs where institution-specific glue goes.
"""

from __future__ import annotations

from aml_framework.spec.models import AMLSpec


def render_dag_stub(spec: AMLSpec) -> str:
    rule_tasks = "\n".join(
        f"    run_{r.id} = PythonOperator(\n"
        f"        task_id='run_{r.id}',\n"
        f"        python_callable=run_rule,\n"
        f"        op_kwargs={{'rule_id': '{r.id}'}},\n"
        f"    )"
        for r in spec.rules
    )
    chain = " >> ".join(f"run_{r.id}" for r in spec.rules)

    return f'''"""Generated DAG stub — tune to your warehouse.

Do not hand-edit detection logic here; edit aml.yaml and regenerate.
Source spec: {spec.program.name} (effective {spec.program.effective_date.isoformat()})
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def run_rule(rule_id: str, **context):
    # TODO: wire to your warehouse and call aml_framework.engine.runner.run_rule(...)
    raise NotImplementedError


default_args = {{
    "owner": "{spec.program.owner}",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}}

with DAG(
    dag_id="{spec.program.name}",
    description="Generated from aml.yaml — do not edit manually.",
    schedule="@hourly",
    start_date=datetime.fromisoformat("{spec.program.effective_date.isoformat()}"),
    catchup=False,
    default_args=default_args,
    tags=["aml", "generated", "{spec.program.jurisdiction}"],
) as dag:
{rule_tasks}

    {chain}
'''
