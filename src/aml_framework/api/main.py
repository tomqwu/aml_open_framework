"""FastAPI application for the AML Open Framework."""

from __future__ import annotations

import json
import os
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
    is_oidc_enabled,
    require_role,
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


def _safe_spec_path(raw: str) -> Path:
    """Resolve a spec path within the project root. Reject traversal attempts."""
    if not raw or raw.startswith("/") or ".." in raw.replace("\\", "/").split("/"):
        raise HTTPException(status_code=400, detail="Invalid spec_path")
    candidate = (_PROJECT_ROOT / raw).resolve()
    project_root = _PROJECT_ROOT.resolve()
    if not candidate.is_relative_to(project_root):
        raise HTTPException(status_code=400, detail="Invalid spec_path")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Spec not found: {raw}")
    return candidate


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

# --- Rate limiting (simple in-memory) ---
_request_counts: dict[str, list[float]] = {}
_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "600"))  # requests per minute per IP
_RATE_WINDOW_SECONDS = 60
_MAX_TRACKED_IPS = int(os.environ.get("API_RATE_LIMIT_MAX_IPS", "10000"))


def _evict_oldest_ips(counts: dict[str, list[float]], target_size: int) -> None:
    """Evict IPs whose most-recent request is the oldest, until len(counts) <= target.
    Caps memory under IP-rotation attacks."""
    if len(counts) <= target_size:
        return
    sorted_ips = sorted(counts.items(), key=lambda kv: max(kv[1]) if kv[1] else 0.0)
    drop = len(counts) - target_size
    for ip, _ in sorted_ips[:drop]:
        counts.pop(ip, None)


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Simple in-memory rate limiter with per-IP eviction + Retry-After."""
    import time

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _request_counts.get(client_ip, [])
    # Drop entries older than the window.
    fresh = [t for t in window if now - t < _RATE_WINDOW_SECONDS]
    if not fresh:
        # Empty window — don't keep the key, prevents unbounded growth under IP rotation.
        _request_counts.pop(client_ip, None)
    else:
        _request_counts[client_ip] = fresh

    if len(fresh) >= _RATE_LIMIT:
        from starlette.responses import JSONResponse

        # Time until the oldest tracked request leaves the window.
        retry_after = max(1, int(_RATE_WINDOW_SECONDS - (now - fresh[0])))
        return JSONResponse(
            {"detail": "Rate limit exceeded. Try again later."},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    fresh.append(now)
    _request_counts[client_ip] = fresh

    # Cap dict size — under IP rotation, evict the IPs with the oldest activity.
    if len(_request_counts) > _MAX_TRACKED_IPS:
        _evict_oldest_ips(_request_counts, _MAX_TRACKED_IPS)

    return await call_next(request)


# --- OpenTelemetry tracing (optional) ---
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # pragma: no cover

    FastAPIInstrumentor.instrument_app(app)  # pragma: no cover
except ImportError:
    pass  # OpenTelemetry not installed — tracing disabled.


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
    if is_oidc_enabled():
        raise HTTPException(
            status_code=404,
            detail="Local login is disabled when OIDC is configured.",
        )
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
    user: dict[str, Any] = Depends(require_role("admin", "manager", "analyst")),
) -> dict[str, Any]:
    spec_path = _safe_spec_path(req.spec_path)

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
    limit: int = 50,
    offset: int = 0,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    runs = list_runs()
    return {
        "items": runs[offset : offset + limit],
        "total": len(runs),
        "limit": limit,
        "offset": offset,
    }


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
    import logging

    spec_path = _safe_spec_path(req.spec_path)
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
    except Exception as e:
        logging.getLogger("aml.api").warning("validate_spec failed for %s: %s", req.spec_path, e)
        return {"valid": False, "error": "Spec failed validation. See server logs for details."}


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


def _validate_webhook_url(url: str) -> None:
    """Reject webhook URLs that target private/link-local/loopback hosts.

    Set WEBHOOK_ALLOW_PRIVATE=1 to bypass for local dev. Resolved IPs are
    re-checked at fire time so DNS-rebinding attacks against the registered
    hostname don't get to issue requests against private addresses.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if os.environ.get("WEBHOOK_ALLOW_PRIVATE") == "1":
        return

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Webhook URL must be http or https")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Webhook URL has no host")

    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot resolve webhook host: {e}") from e

    for addr_str in addrs:
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
        ):
            raise HTTPException(
                status_code=400,
                detail="Webhook host resolves to a non-routable address (private/loopback/link-local).",
            )


@app.post("/api/v1/webhooks")
async def register_webhook(
    config: WebhookConfig,
    user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Register a webhook URL for event notifications."""
    _validate_webhook_url(config.url)
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
    user: dict[str, Any] = Depends(require_role("admin", "manager", "analyst")),
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
                # Re-validate before firing — guards against DNS rebinding between
                # registration and dispatch.
                _validate_webhook_url(hook["url"])
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
