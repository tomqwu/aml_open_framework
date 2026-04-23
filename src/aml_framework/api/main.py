"""FastAPI application for the AML Open Framework."""

from __future__ import annotations

import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from aml_framework.api.auth import (
    DEMO_USERS,
    create_token,
    get_current_user,
)
from aml_framework.api.db import (
    get_run,
    get_run_alerts,
    get_run_metrics,
    init_db,
    list_runs,
    store_run,
)
from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AML Open Framework API",
    version="0.1.0",
    description="Spec-driven AML compliance automation — REST interface.",
    lifespan=lifespan,
)


# --- Models ---


class LoginRequest(BaseModel):
    username: str
    password: str


class RunRequest(BaseModel):
    spec_path: str = "examples/canadian_schedule_i_bank/aml.yaml"
    seed: int = 42


# --- Endpoints ---


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/login")
async def login(req: LoginRequest) -> dict[str, str]:
    user = DEMO_USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username, user["role"])
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.post("/api/v1/runs")
async def create_run(
    req: RunRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    spec_path = _PROJECT_ROOT / req.spec_path
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {req.spec_path}")

    spec = load_spec(spec_path)
    as_of = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    data = generate_dataset(as_of=as_of, seed=req.seed)

    artifacts = Path(tempfile.mkdtemp(prefix="aml_api_"))
    result = run_spec(
        spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=artifacts,
    )

    run_id = str(uuid.uuid4())[:8]
    manifest = result.manifest
    manifest["run_id"] = run_id

    # Persist to PostgreSQL if configured.
    alerts_dict = {
        rule_id: [_serialize(a) for a in alerts]
        for rule_id, alerts in result.alerts.items()
    }
    store_run(
        run_id=run_id,
        spec_path=req.spec_path,
        seed=req.seed,
        manifest=manifest,
        alerts=alerts_dict,
        metrics=[m.to_dict() for m in result.metrics],
    )

    return {
        "run_id": run_id,
        "total_alerts": result.total_alerts,
        "total_cases": len(result.case_ids),
        "total_metrics": len(result.metrics),
        "reports": sorted(result.reports.keys()),
    }


@app.get("/api/v1/runs")
async def get_runs(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return list_runs()


@app.get("/api/v1/runs/{run_id}")
async def get_run_detail(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    manifest = get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Run not found")
    return manifest


@app.get("/api/v1/runs/{run_id}/alerts")
async def get_alerts(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return get_run_alerts(run_id)


@app.get("/api/v1/runs/{run_id}/metrics")
async def get_metrics(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return get_run_metrics(run_id)


def _serialize(obj: Any) -> Any:
    """Convert non-JSON-serializable types (Decimal, datetime) to primitives."""
    if hasattr(obj, "items"):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    try:
        float(obj)
        return float(obj)
    except (TypeError, ValueError):
        return obj
