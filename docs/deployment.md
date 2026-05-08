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
| `AML_ENV` / `API_ENV` | Set to `production` for non-demo API startup gates | yes (prod) | unset (dev/demo mode) |
| `COSMOS_ENDPOINT` | Cosmos DB account endpoint for run / case persistence (Sponsorship-sub-friendly alternative to Postgres). When set, takes precedence over `DATABASE_URL`. Auth uses `DefaultAzureCredential` — pair with managed-identity / workload-identity + Cosmos Built-in Data Contributor role. | yes for Cosmos deployments | unset |
| `COSMOS_DATABASE` | Cosmos database name. | optional | `aml` |
| `DATABASE_URL` | Postgres URL for run / case persistence (used when `COSMOS_ENDPOINT` is unset). | yes for Postgres prod deployments | SQLite if both `COSMOS_ENDPOINT` and `DATABASE_URL` are unset |
| `JWT_SECRET` | HMAC secret for API tokens (32+ bytes) | yes (prod) | random per-process secret in dev/demo mode only |
| `ALLOW_DEMO_AUTH` | Explicitly re-enable built-in demo users in production | no | unset / disabled in production |
| `OIDC_ISSUER_URL` | OIDC discovery endpoint for SSO | recommended (prod) | unset (built-in users in dev only) |
| `OIDC_AUDIENCE` | Expected `aud` claim | required when `OIDC_ISSUER_URL` is set | unset |
| `OIDC_ALLOW_MISSING_AUDIENCE` | Disable OIDC audience verification for local-only testing | no (dev only) | unset |
| `OIDC_ROLE_CLAIM` | Claim path used for API role mapping | optional | `roles` |
| `OIDC_TENANT_CLAIM` | Claim path used for tenant isolation | optional | `tid` |
| `OIDC_ALLOWED_TENANTS` | Comma-separated tenant allowlist | optional | unset |
| `API_RATE_LIMIT` | Per-IP requests per minute | no | `600` |
| `API_DATA_ROOTS` | Local file roots allowed for API CSV/Parquet/ISO20022/DuckDB sources | no | `data` |
| `API_UPLOAD_ROOT` | Tenant-scoped upload storage root | no | `data/uploads` |
| `API_ARTIFACT_ROOT` | API run artifact storage root | no | `data/api-artifacts` |
| `API_MAX_UPLOAD_BYTES` | Max size for each uploaded CSV file | no | `26214400` |
| `API_ALLOW_REMOTE_DATA_SOURCES` | Enable API access to S3/GCS/Snowflake/BigQuery sources | no | unset |
| `SPEC_PATH` | Spec file the dashboard loads | no | `examples/canadian_schedule_i_bank/aml.yaml` |
| `JIRA_URL`, `JIRA_TOKEN`, `JIRA_PROJECT` | Jira case sync | optional | unset (no-op) |
| `SLACK_WEBHOOK_URL` | Slack alert push | optional | unset (no-op) |
| `TEAMS_WEBHOOK_URL` | Teams alert push | optional | unset (no-op) |

**Persistence-backend selection (highest priority first):**

1. `COSMOS_ENDPOINT` set → Azure Cosmos DB. Required combination for Azure
   Sponsorship subscriptions where Postgres Flexible Server is region-locked
   in every available region. Uses `DefaultAzureCredential`; needs a
   managed-identity (Container Apps UAMI / AKS workload-identity) granted the
   "Cosmos DB Built-in Data Contributor" role on the account.
2. `DATABASE_URL` set (and `COSMOS_ENDPOINT` unset) → PostgreSQL via psycopg2.
   The default for PAYG / EA / MCA Azure subscriptions and self-hosted
   deployments.
3. Otherwise → local SQLite at `~/.aml_framework/runs.db`. Fine for demos,
   **never** for production.

Production mode is enabled with
`AML_ENV=production` or `API_ENV=production`; in that mode the API refuses to
start without `JWT_SECRET` and disables the built-in demo users unless
`ALLOW_DEMO_AUTH=true` is set deliberately. Outside production mode, an unset
`JWT_SECRET` logs a warning and uses a random per-process secret, so locally
issued JWTs do not survive a restart.

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

The dashboard renders at <http://localhost:8501>. In local/demo mode the API
ships default demo users: `admin / admin`, `analyst / analyst`,
`auditor / auditor`, `manager / manager`. Do not use those credentials for
production: set `AML_ENV=production`, configure `JWT_SECRET`, and prefer OIDC.

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

Set `postgres.enabled=false` and provide `database.url`. The chart stores it in
the release secret as `database-url` and the API deployment reads from that key:

```yaml
postgres:
  enabled: false
database:
  url: postgresql://...
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
- [ ] Configure `OIDC_ROLE_CLAIM`, `OIDC_TENANT_CLAIM`, and `OIDC_ALLOWED_TENANTS`.
- [ ] Set `API_DATA_ROOTS` and leave remote API sources disabled unless explicitly needed.
- [ ] Set `API_RATE_LIMIT` appropriate to expected load.
- [ ] Mount your real `aml.yaml` from a ConfigMap, secret, or PVC.
- [ ] Configure ingress TLS (cert-manager / managed cert).
- [ ] Confirm retention policy values in `aml.yaml` match institutional policy.
- [ ] Validate the spec in CI: `aml validate path/to/aml.yaml`.
- [ ] Wire `aml verify` into a scheduled job to detect audit-ledger tampering.

## Deploying on Azure / AKS

For banks deploying on Microsoft Azure, the framework supports a
zero-static-secrets shape via workload identity + Key Vault + Entra ID
OIDC. All Azure-specific behaviour is opt-in via the existing Helm
chart — leave the `azure:` block empty for an Azure-agnostic install
identical to the on-prem deployment.

A reference values file ships at `deploy/helm/values-azure.example.yaml`.

### Prerequisites

```bash
# 1. Create the AKS cluster with OIDC issuer + workload identity.
az aks create --resource-group <rg> --name <cluster> \
  --enable-oidc-issuer --enable-workload-identity \
  --node-count 3

# 2. Get the OIDC issuer URL (needed for federated identity creds).
export OIDC_URL=$(az aks show -g <rg> -n <cluster> \
  --query oidcIssuerProfile.issuerUrl -o tsv)

# 3. Create a user-assigned managed identity for the workload.
az identity create --resource-group <rg> --name aml-workload

# 4. Create Key Vault + grant the managed identity Secrets User.
az keyvault create --name kv-bank-aml-prod --resource-group <rg>
az role assignment create --role "Key Vault Secrets User" \
  --assignee $(az identity show -g <rg> -n aml-workload --query principalId -o tsv) \
  --scope $(az keyvault show -g <rg> -n kv-bank-aml-prod --query id -o tsv)

# 5. Federate the managed identity to the chart's ServiceAccounts.
az identity federated-credential create --name aml-api-fic \
  --identity-name aml-workload --resource-group <rg> \
  --issuer "$OIDC_URL" \
  --subject "system:serviceaccount:default:<release>-api" \
  --audiences api://AzureADTokenExchange

az identity federated-credential create --name aml-dashboard-fic \
  --identity-name aml-workload --resource-group <rg> \
  --issuer "$OIDC_URL" \
  --subject "system:serviceaccount:default:<release>-dashboard" \
  --audiences api://AzureADTokenExchange
```

### Install

```bash
# Copy the example file and fill in the placeholders.
cp deploy/helm/values-azure.example.yaml my-values.yaml
# Edit: image.repository, oidc.issuerUrl + audience + allowedTenants,
# azure.workloadIdentityClientId, azure.keyVaultName,
# azure.storageAccountName, optionally synapseConnString /
# azureSqlConnString, ingress.host.

helm install aml ./deploy/helm -f my-values.yaml
```

### What workload identity buys you

When `azure.workloadIdentityClientId` is set, the chart:

1. Renders a `ServiceAccount` with the `azure.workload.identity/client-id` annotation for both the API and dashboard pods.
2. Adds the `azure.workload.identity/use: "true"` pod label so the AKS webhook injects the OIDC token.
3. Threads `AZURE_KEY_VAULT_NAME` + `AZURE_STORAGE_ACCOUNT_NAME` (and Synapse / Azure SQL conn strings) as env vars.

Inside the pod, every Azure SDK call (`SecretClient`, `BlobServiceClient`, `pyodbc` with `Authentication=ActiveDirectoryMsi`) automatically picks up the federated identity. No client secrets, no managed-identity ARM ID lookups, no cert rotation.

### Data sources

After install, the dashboard + API pick up Azure data sources via the new types added in PR-AZ-1:

| Source type | URI / connection |
|---|---|
| `azure_blob` / `adls` | `--data-dir abfss://<container>@<account>.dfs.core.windows.net/<path>` |
| `synapse` | ODBC connection string in `--data-dir` (or env var `AZURE_SYNAPSE_CONN`) |
| `azuresql` | ODBC connection string in `--data-dir` (or env var `AZURE_SQL_CONN`) |

The Round-12 lineage chain (`walk_lineage(case_id)`) picks up Azure-sourced runs unchanged — `source_path` shows `azure_blob:abfss://…/txn`, `synapse:DRIVER=…#trades`, etc.

### Production checklist (Azure additions)

- [ ] Federated identity credentials created BEFORE `helm install`.
- [ ] Key Vault populated: `JWT-SECRET`, `OPENAI-API-KEY` (note the dashes — Key Vault disallows underscores; the SecretsProvider translates `_`→`-` automatically).
- [ ] Entra ID app registration created with `roles` claim + `tid` claim mapped (the chart's defaults).
- [ ] App roles defined in Entra ID match `analyst` / `auditor` / `manager` / `admin`.
- [ ] `oidc.allowedTenants` set to the tenant ID — single-tenant by default.
- [ ] AKS cluster RBAC scoped per-namespace; the Key Vault role binding is on the managed identity, not the SA token.
- [ ] Storage account configured with Hierarchical Namespace (ADLS Gen2) for `azure_blob`/`adls` sources.

## Deploying on Azure via the cloud landing zone (Container Apps)

For banks consuming the prebuilt landing zone at
[tomqwu/cloud_landing_zone_for_ai_coding](https://github.com/tomqwu/cloud_landing_zone_for_ai_coding),
the framework ships a Terraform module under `deploy/terraform/`
that deploys to Container Apps with one of two Entra-ID-authenticated
persistence backends:

- **Postgres Flexible Server** (B1ms) — default for PAYG / EA / MCA
  subscriptions.
- **Cosmos DB serverless** — alternative for Azure Sponsorship
  subscriptions where Postgres Flexible Server returns
  `LocationIsOfferRestricted` in every available region. Set
  `enable_cosmos = true` and `enable_postgres = false` in
  `terraform.tfvars`. The module provisions a Cosmos account, the
  `aml` database, four containers (`runs`, `run_alerts`,
  `run_metrics`, `spec_versions`, partition key `/tenant_id`), grants
  the per-app UAMI the Cosmos Built-in Data Contributor role, and
  wires `COSMOS_ENDPOINT` / `COSMOS_DATABASE` into both Container
  Apps. The Python persistence layer
  (`src/aml_framework/api/db.py`) selects Cosmos automatically when
  `COSMOS_ENDPOINT` is set.

This is the alternative path to the AKS Helm chart above.

The landing zone's CLAUDE.md forbids AKS, so this is the *required*
path when consuming that landing zone. For self-managed Azure (no
landing zone) the AKS Helm chart above remains the recommended
shape.

Detailed cookbook: [`deploy/terraform/README.md`](../deploy/terraform/README.md).
Quick version:

```bash
cd deploy/terraform

terraform init \
  -backend-config="resource_group_name=<from landing zone bootstrap>" \
  -backend-config="storage_account_name=<from landing zone bootstrap>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=aml-compliance.tfstate"

cat > terraform.tfvars <<EOF
env                              = "dev"
owner_email                      = "you@example.com"
github_repo                      = "tomqwu/aml_open_framework"
platform_tfstate_resource_group  = "<from landing zone>"
platform_tfstate_storage_account = "<from landing zone>"
platform_tfstate_container       = "tfstate"

# Persistence backend — pick exactly one:
#   Postgres (default, PAYG/EA/MCA subs):
#     enable_postgres = true
#   Cosmos serverless (Sponsorship subs where Postgres is region-locked):
#     enable_postgres = false
#     enable_cosmos   = true
#     # cosmos_database_name = "aml"   # optional
EOF

terraform apply
```

Cost expectations on top of the landing zone's $5/mo baseline:

| Component | Approx. monthly |
|---|---|
| Container App API (min 1 replica) | ~$10 |
| Container App dashboard | ~$10 |
| Postgres Flexible Server B1ms (`enable_postgres=true`) | ~$13 (or $0 with the Sponsorship-sub free tier in canadacentral) |
| Cosmos DB serverless (`enable_cosmos=true`) | ~$0 idle (no provisioned RU/s) |
| **Total** (Postgres) | **~$33/mo** |
| **Total** (Cosmos) | **~$20/mo** |

After install, populate the per-app Key Vault with `JWT-SECRET` (and
optionally `OPENAI-API-KEY` for the GenAI co-pilot). Subsequent
deploys go through `.github/workflows/deploy-azure-landing-zone.yml` —
push to main, federated-identity OIDC handles auth, revision rolls
over automatically.

See [`audit-evidence.md`](audit-evidence.md) for the evidence bundle contract
and [`architecture.md`](architecture.md) for the layered runtime view.
