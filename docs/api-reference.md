# REST API Reference

Static reference for the FastAPI layer (`src/aml_framework/api/main.py`). The
live interactive Swagger UI is available at `http://localhost:8000/docs` once
the API is running.

```bash
aml api --port 8000
# or in Docker Compose:
docker-compose up api
```

## Conventions

- **Base URL**: `/api/v1`
- **Auth**: HTTP `Authorization: Bearer <token>` header. Tokens are obtained
  from `POST /api/v1/login` (see [Authentication](#authentication)).
- **Content type**: `application/json` for all request and response bodies
  unless noted (`multipart/form-data` for `/upload`).
- **Rate limit**: 600 requests/minute per IP by default. Configurable via
  `API_RATE_LIMIT` env var. Exceeding the limit returns `429 Too Many Requests`.
- **Errors**: standard FastAPI shape — `{"detail": "<message>"}` with the
  appropriate HTTP status.

## Authentication

The reference implementation ships demo users (`admin`, `analyst`, `auditor`,
`manager`, all with password equal to username). Replace the auth backend before
any non-demo deployment, or configure OIDC via `OIDC_ISSUER_URL` /
`OIDC_AUDIENCE`. Role and tenant claims are configurable with
`OIDC_ROLE_CLAIM` and `OIDC_TENANT_CLAIM`; use `OIDC_ALLOWED_TENANTS` to reject
tokens from unexpected tenants.

### `POST /api/v1/login`

Issue a JWT for an authenticated user.

Request:

```json
{ "username": "admin", "password": "admin" }
```

Response `200`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "admin",
  "tenant": "bank_a"
}
```

Errors: `401` on invalid credentials.

## Health

### `GET /api/v1/health`

Liveness probe. **Unauthenticated.**

Response `200`:

```json
{ "status": "ok", "version": "0.1.0" }
```

## Runs

A *run* is a single execution of the engine against a spec and a data source.
Runs persist to PostgreSQL when `DATABASE_URL` is set (otherwise SQLite).

### `POST /api/v1/runs`

Execute the engine.

Request:

```json
{
  "spec_path": "examples/canadian_schedule_i_bank/aml.yaml",
  "seed": 42,
  "data_source": "synthetic",
  "data_dir": null
}
```

Fields:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `spec_path` | string | `examples/canadian_schedule_i_bank/aml.yaml` | Path relative to project root |
| `seed` | integer | `42` | Synthetic data seed; ignored for non-synthetic sources |
| `data_source` | string | `synthetic` | One of `synthetic`, `csv`, `parquet`, `duckdb`, `iso20022`, `s3`, `gcs`, `snowflake`, `bigquery` |
| `data_dir` | string \| null | `null` | Required for CSV, Parquet, ISO20022, S3, GCS, Snowflake, and BigQuery |
| `db_path` | string \| null | `null` | Required for DuckDB |

For API calls, local file inputs must resolve under `API_DATA_ROOTS` (default:
`data`). Remote sources (`s3`, `gcs`, `snowflake`, `bigquery`) are disabled
unless `API_ALLOW_REMOTE_DATA_SOURCES=1`.

Response `200`:

```json
{
  "run_id": "a1b2c3d4",
  "total_alerts": 17,
  "total_cases": 9,
  "total_metrics": 13,
  "reports": ["business_owner_daily", "developer_runtime", "..."]
}
```

Errors: `404` if `spec_path` is not found.

Side effects: persists the run, stores a spec-version snapshot, and fires any
registered webhooks for `run_completed` and (when alerts > 0) `alert_created`.

### `GET /api/v1/runs`

List persisted runs (newest first).

Query parameters:

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | integer | `50` | Page size |
| `offset` | integer | `0` | Items to skip |

Response `200`:

```json
{
  "items": [{ "run_id": "...", "spec_path": "...", "created_at": "..." }],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

### `GET /api/v1/runs/{run_id}`

Return the manifest for a single run (spec hash, input hash, output hashes,
engine version, timing).

Errors: `404` if the run does not exist.

### `GET /api/v1/runs/{run_id}/alerts`

Return all alerts produced by the run, grouped by `rule_id`.

### `GET /api/v1/runs/{run_id}/metrics`

Return all metric evaluations (with RAG band) for the run.

### `GET /api/v1/runs/{run_id}/reports`

Return the list of report ids produced by the run. Reports are rendered, not
persisted — re-run the engine or use the CLI (`aml report`) to materialise
markdown.

### `GET /api/v1/runs/{run_id}/alerts/cef`

Export alerts as Common Event Format for SIEM ingestion.

Response `200`:

```json
{ "format": "cef", "data": "CEF:0|AML Open Framework|engine|0.1.0|...|" }
```

Errors: `404` when the run is unknown or has zero alerts.

## Specs

### `POST /api/v1/validate`

Validate a spec without executing it.

Request: same shape as `POST /runs`.

Response `200` (valid):

```json
{
  "valid": true,
  "program": "td_bank_us",
  "jurisdiction": "CA",
  "rules": 6,
  "metrics": 13,
  "queues": 3
}
```

Response `200` (invalid):

```json
{ "valid": false, "error": "Spec failed validation. See server logs for details." }
```

Errors: `404` if `spec_path` is not found.

### `GET /api/v1/specs`

List spec versions stored for the calling user's tenant. Each entry includes
`spec_hash`, `program_name`, `tenant_id`, and `created_at`.

## Webhooks

In-memory, tenant-scoped registration of HTTP callbacks fired on engine events.
Suitable for demos and local integration tests; persist to your message bus in
production. Webhook secrets are stored for signing only and are not returned by
the list endpoint.

### `POST /api/v1/webhooks`

Register a webhook.

Request:

```json
{
  "name": "ops-slack",
  "url": "https://hooks.slack.com/services/...",
  "events": ["alert_created", "run_completed"],
  "secret": "optional-shared-signing-secret"
}
```

Supported events: `alert_created`, `run_completed`.

### `GET /api/v1/webhooks`

List registered webhooks for the calling user's tenant. The response includes
`signed: true` when a signing secret is configured, but never returns the
secret.

## Data upload

### `POST /api/v1/upload`

Tenant-scoped `multipart/form-data` CSV upload. Pass one or both file fields:
`txn_file` and `customer_file`. The API stores them under `API_UPLOAD_ROOT`
(default `data/uploads`) and returns a `data_dir` for a follow-up
`POST /runs` request with `data_source=csv`.

Response `200`:

```json
{
  "status": "uploaded",
  "tenant": "bank_a",
  "upload_id": "a1b2c3d4",
  "data_dir": "/abs/path/data/uploads/bank_a/a1b2c3d4",
  "files": ["txn.csv", "customer.csv"]
}
```

## Endpoint summary

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/health` | – | Liveness probe |
| `POST` | `/api/v1/login` | – | Issue a JWT |
| `POST` | `/api/v1/runs` | required | Execute the engine |
| `GET` | `/api/v1/runs` | required | List runs (paginated) |
| `GET` | `/api/v1/runs/{run_id}` | required | Run manifest |
| `GET` | `/api/v1/runs/{run_id}/alerts` | required | Alerts by rule |
| `GET` | `/api/v1/runs/{run_id}/metrics` | required | Metric values + RAG |
| `GET` | `/api/v1/runs/{run_id}/reports` | required | Report ids |
| `GET` | `/api/v1/runs/{run_id}/alerts/cef` | required | CEF export for SIEM |
| `POST` | `/api/v1/validate` | required | Validate a spec |
| `GET` | `/api/v1/specs` | required | List stored spec versions |
| `POST` | `/api/v1/webhooks` | required | Register a webhook |
| `GET` | `/api/v1/webhooks` | required | List webhooks |
| `POST` | `/api/v1/upload` | required | Upload data (stub) |

See [`deployment.md`](deployment.md) for environment variables and
[`audit-evidence.md`](audit-evidence.md) for the run-manifest contract.
