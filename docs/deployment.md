# Deployment

The framework ships three deployable artifacts:

- **CLI / library** — `pip install -e ".[dev,dashboard,api]"` for local use.
- **Docker Compose** — single-host stack (PostgreSQL + API + Dashboard).
- **Helm chart** — Kubernetes deployment under `deploy/helm/`.

This document covers Compose and Helm. For development use, see the
[Quickstart](../README.md#quickstart) in the project README.

## Configuration model

Every deployment surface reads the same set of environment variables. Copy
`.env.example` to `.env` and edit before bringing services up.

| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| `DATABASE_URL` | Postgres URL for run / case persistence | yes (prod) | SQLite if unset |
| `JWT_SECRET` | HMAC secret for API tokens | yes (prod) | `aml-framework-dev-secret` |
| `OIDC_ISSUER_URL` | OIDC discovery endpoint for SSO | optional | unset (built-in users) |
| `OIDC_AUDIENCE` | Expected `aud` claim | optional | unset |
| `API_RATE_LIMIT` | Per-IP requests per minute | no | `600` |
| `SPEC_PATH` | Spec file the dashboard loads | no | `examples/canadian_schedule_i_bank/aml.yaml` |
| `JIRA_URL`, `JIRA_TOKEN`, `JIRA_PROJECT` | Jira case sync | optional | unset (no-op) |
| `SLACK_WEBHOOK_URL` | Slack alert push | optional | unset (no-op) |
| `TEAMS_WEBHOOK_URL` | Teams alert push | optional | unset (no-op) |

When `DATABASE_URL` is unset the API falls back to local SQLite — fine for
demos, **never** for production. When `JWT_SECRET` is unset the API logs a
warning and refuses to issue tokens against an OIDC-only configuration.

## Docker Compose

`docker-compose.yml` defines three services on a single host:

```bash
cp .env.example .env
# edit JWT_SECRET, DATABASE_URL, and any integrations
docker-compose up --build
```

| Service | Image | Port | Depends on |
|---------|-------|------|-----------|
| `postgres` | `postgres:16-alpine` | `5432` | – |
| `api` | built from `Dockerfile` | `8000` | `postgres` healthy |
| `dashboard` | built from `Dockerfile` | `8501` | – |

Volumes:

- `pgdata` → `/var/lib/postgresql/data` (Postgres data files; survives `docker-compose down`).

The `api` container runs `uvicorn aml_framework.api.main:app`; the `dashboard`
container runs `streamlit run src/aml_framework/dashboard/app.py`. Both are
built from the same image — `Dockerfile` installs the project with the
`[dev,dashboard,api]` extras.

### Health checks

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","version":"..."}
```

The dashboard renders at <http://localhost:8501>. Default demo users for the
API: `admin / admin`, `analyst / analyst`, `auditor / auditor`,
`manager / manager`. Replace the auth backend before any non-demo use.

### Tear down

```bash
docker-compose down            # keeps the pgdata volume
docker-compose down --volumes  # wipes Postgres
```

## Helm

The chart under `deploy/helm/` deploys API, Dashboard, and an optional
in-cluster Postgres. See `deploy/helm/README.md` for the rendered parameter
table; the full set of values lives in `deploy/helm/values.yaml`.

### Build and push the image

```bash
docker build -t your-registry/aml-framework:0.1.0 .
docker push your-registry/aml-framework:0.1.0
```

### Install

```bash
helm install aml ./deploy/helm/ \
  --set image.repository=your-registry/aml-framework \
  --set image.tag=0.1.0 \
  --set jwt.secret="$(openssl rand -hex 32)" \
  --set postgres.password="$(openssl rand -hex 16)"
```

### Common overrides

```yaml
# values-prod.yaml
image:
  repository: registry.example.com/aml-framework
  tag: "0.1.0"

api:
  replicas: 3
  resources:
    requests: { cpu: "500m", memory: "1Gi" }
    limits:   { cpu: "2",    memory: "4Gi" }

dashboard:
  replicas: 2
  spec: /etc/aml/spec/aml.yaml   # mounted from a ConfigMap or PVC

postgres:
  enabled: false                  # use a managed Postgres (RDS, Cloud SQL)

ingress:
  enabled: true
  host: aml.example.com
```

```bash
helm upgrade --install aml ./deploy/helm/ -f values-prod.yaml
```

### External Postgres

Set `postgres.enabled=false` and provide `DATABASE_URL` via a Kubernetes
secret (the API deployment template reads it from `aml-framework-secrets`):

```bash
kubectl create secret generic aml-framework-secrets \
  --from-literal=DATABASE_URL='postgresql://...' \
  --from-literal=JWT_SECRET="$(openssl rand -hex 32)"
```

### Uninstall

```bash
helm uninstall aml
```

The PVC backing in-cluster Postgres survives `helm uninstall`. Delete it
explicitly when wiping state:

```bash
kubectl delete pvc -l app.kubernetes.io/instance=aml
```

## Production checklist

Before exposing any deployment to non-demo traffic:

- [ ] Replace `JWT_SECRET` with a long random value (32+ bytes).
- [ ] Replace `postgres.password` (or move to a managed database).
- [ ] Replace the demo user backend (`api/main.py`) with OIDC or your IdP.
- [ ] Set `API_RATE_LIMIT` appropriate to expected load.
- [ ] Mount your real `aml.yaml` from a ConfigMap, secret, or PVC.
- [ ] Configure ingress TLS (cert-manager / managed cert).
- [ ] Confirm retention policy values in `aml.yaml` match institutional policy.
- [ ] Validate the spec in CI: `aml validate path/to/aml.yaml`.
- [ ] Wire `aml verify` into a scheduled job to detect audit-ledger tampering.

See [`audit-evidence.md`](audit-evidence.md) for the evidence bundle contract
and [`architecture.md`](architecture.md) for the layered runtime view.
