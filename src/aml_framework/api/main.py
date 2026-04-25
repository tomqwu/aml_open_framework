"""FastAPI application for the AML Open Framework."""

from __future__ import annotations

import json
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
    list_spec_versions,
    store_run,
    store_spec_version,
)
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # pragma: no cover
    yield  # pragma: no cover


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
    data_source: str = "synthetic"
    data_dir: str | None = None


# --- Endpoints ---


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/login")
async def login(req: LoginRequest) -> dict[str, str]:
    user = DEMO_USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username, user["role"], user.get("tenant", "default"))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "tenant": user.get("tenant", "default"),
    }


@app.post("/api/v1/runs")
async def create_run(
    req: RunRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    spec_path = _PROJECT_ROOT / req.spec_path
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {req.spec_path}")

    from aml_framework.data.sources import resolve_source

    spec = load_spec(spec_path)
    as_of = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    data = resolve_source(
        source_type=req.data_source,
        spec=spec,
        as_of=as_of,
        seed=req.seed,
        data_dir=req.data_dir,
    )

    artifacts = Path(tempfile.mkdtemp(prefix="aml_api_"))
    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of,
        artifacts_root=artifacts,
    )

    run_id = str(uuid.uuid4())[:8]
    manifest = result.manifest
    manifest["run_id"] = run_id

    # Persist to PostgreSQL if configured.
    alerts_dict = {
        rule_id: [_serialize(a) for a in alerts] for rule_id, alerts in result.alerts.items()
    }
    store_run(
        run_id=run_id,
        spec_path=req.spec_path,
        seed=req.seed,
        manifest=manifest,
        alerts=alerts_dict,
        metrics=[m.to_dict() for m in result.metrics],
    )

    # Store spec version for tracking.
    store_spec_version(
        spec_hash=manifest.get("spec_content_hash", ""),
        spec_content=spec_path.read_text(encoding="utf-8"),
        program_name=spec.program.name,
        tenant_id=user.get("tenant", "default"),
    )

    run_summary = {
        "run_id": run_id,
        "total_alerts": result.total_alerts,
        "total_cases": len(result.case_ids),
        "total_metrics": len(result.metrics),
        "reports": sorted(result.reports.keys()),
    }

    # Fire registered webhooks.
    _fire_webhooks("run_completed", run_summary)
    if result.total_alerts > 0:
        _fire_webhooks(
            "alert_created",
            {
                "run_id": run_id,
                "alert_count": result.total_alerts,
            },
        )

    return run_summary


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


@app.post("/api/v1/validate")
async def validate_spec(
    req: RunRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a spec without running it."""
    spec_path = _PROJECT_ROOT / req.spec_path
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {req.spec_path}")
    try:
        spec = load_spec(spec_path)
        return {
            "valid": True,
            "program": spec.program.name,
            "jurisdiction": spec.program.jurisdiction,
            "rules": len(spec.rules),
            "metrics": len(spec.metrics),
            "queues": len(spec.workflow.queues),
        }
    except (ValueError, Exception) as e:
        return {"valid": False, "error": str(e)}


@app.get("/api/v1/runs/{run_id}/reports")
async def get_reports(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Get report list for a run (reports are not persisted — returns IDs only)."""
    manifest = get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"reports": manifest.get("reports", [])}


# --- Webhook configuration ---
_webhooks: list[dict[str, str]] = []


class WebhookConfig(BaseModel):
    url: str
    events: list[str] = ["alert_created", "run_completed"]
    name: str = "default"


@app.post("/api/v1/webhooks")
async def register_webhook(
    config: WebhookConfig,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Register a webhook URL for event notifications."""
    _webhooks.append({"name": config.name, "url": config.url, "events": config.events})
    return {"status": "registered", "name": config.name, "event_count": len(config.events)}


@app.get("/api/v1/webhooks")
async def list_webhooks(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict]:
    return _webhooks


@app.post("/api/v1/upload")
async def upload_data(
    txn_file: Any = None,
    customer_file: Any = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Upload CSV files for a run. Use with multipart/form-data."""
    # This is a stub — full implementation would save files to data/input/
    # and trigger a run. For now, document the interface.
    return {
        "status": "upload endpoint ready",
        "note": "Use POST /api/v1/runs with data_source=csv and data_dir pointing to uploaded files",
    }


@app.get("/api/v1/specs")
async def get_specs(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List stored spec versions."""
    tenant = user.get("tenant", "default")
    return list_spec_versions(tenant_id=tenant)


@app.get("/api/v1/runs/{run_id}/alerts/cef")
async def get_alerts_cef(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Export alerts in CEF format for SIEM ingestion."""
    from aml_framework.integrations.siem import export_cef

    alerts_data = get_run_alerts(run_id)
    if not alerts_data:
        raise HTTPException(status_code=404, detail="Run not found or no alerts")
    alerts_dict = {a["rule_id"]: a["alerts"] for a in alerts_data}
    sev_map = {a["rule_id"]: "medium" for a in alerts_data}  # Default severity.
    return {"format": "cef", "data": export_cef(alerts_dict, sev_map)}


def _fire_webhooks(event: str, payload: dict[str, Any]) -> None:
    """POST to all registered webhooks matching the event."""
    import logging

    logger = logging.getLogger("aml.webhooks")
    for hook in _webhooks:
        if event in hook.get("events", []):
            try:
                import urllib.request

                data = json.dumps({"event": event, **payload}).encode("utf-8")
                req = urllib.request.Request(
                    hook["url"],
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
                logger.info("Webhook %s fired for %s", hook["name"], event)
            except Exception as e:
                logger.warning("Webhook %s failed: %s", hook["name"], e)


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
