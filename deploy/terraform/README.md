# Azure Landing-Zone Deployment

Deploys the AML compliance framework to Microsoft Azure on top of the
[cloud landing zone](https://github.com/tomqwu/cloud_landing_zone_for_ai_coding).
Container Apps (no AKS), Application Insights via OpenTelemetry,
secrets in the landing zone's per-app Key Vault, and one of two
Entra-ID-authenticated persistence backends:

- **Postgres Flexible Server** (B1ms) — default for PAYG / EA / MCA
  subscriptions where the Postgres free tier is offered in the
  platform region.
- **Cosmos DB serverless** — alternative for Azure Sponsorship
  subscriptions where Postgres Flexible Server returns
  `LocationIsOfferRestricted` in every available region. Set
  `enable_cosmos = true` and `enable_postgres = false` in
  `terraform.tfvars`. The Terraform module provisions a Cosmos
  account, the `aml` database, four containers (`runs`,
  `run_alerts`, `run_metrics`, `spec_versions`, partition key
  `/tenant_id`), grants the per-app UAMI the Cosmos Built-in Data
  Contributor role, and wires `COSMOS_ENDPOINT` / `COSMOS_DATABASE`
  into both Container Apps. The Python persistence layer
  (`src/aml_framework/api/db.py`) selects Cosmos automatically when
  `COSMOS_ENDPOINT` is set.

For the AKS Helm chart deployment shape (banks deploying on their own
AKS or on-prem K8s), see `deploy/helm/` and the "Deploying on Azure /
AKS" section of `docs/deployment.md`.

## Dashboard persistence asymmetry (known issue on the Postgres path)

The dashboard Container App receives `COSMOS_ENDPOINT` and
`COSMOS_DATABASE` env vars but does **not** receive `DATABASE_URL`.
The dashboard's Run History (page 15) and Comparative Analytics
(page 19) call `aml_framework.api.db.list_runs()` directly using
whichever env the dashboard pod sees, so:

- **Cosmos backend (`enable_cosmos = true`)**: dashboard pod has
  `COSMOS_ENDPOINT` set, `_active_backend()` resolves to `cosmos`,
  pages query the same Cosmos containers the API writes to. Works
  correctly.
- **Postgres backend (`enable_postgres = true`)**: dashboard pod has
  neither `DATABASE_URL` nor `COSMOS_ENDPOINT`, `_active_backend()`
  resolves to `sqlite`, and `list_runs()` reads from an empty local
  SQLite file inside the dashboard container — disconnected from the
  Postgres database the API writes to. Run History and Comparative
  Analytics show stale-or-empty results even when the API and
  Postgres are both healthy.

The Helm chart calls out the same shape in
`deploy/helm/templates/dashboard-deployment.yaml`. Resolving this is
queued for a future round (options: wire `DATABASE_URL` and the
Postgres-admin UAMI into the dashboard pod, or refactor the dashboard
pages to call the API's `/runs` endpoints over HTTP). Until then,
operators running on Postgres should know that Run History and
Comparative Analytics are not driven by the deployment's Postgres
database — investigating empty views means looking at the dashboard's
persistence wiring, not API reachability.

## Prerequisites

1. **The landing zone is bootstrapped** in the user's Azure
   subscription. See its README for the one-time `bootstrap/`
   apply that creates the tfstate Storage Account + the
   GitHub-Actions managed identity.

2. **The platform layer is deployed.** From the landing zone repo:
   `cd platform && terraform init && terraform apply`. Capture the
   bootstrap outputs (`tfstate_resource_group`,
   `tfstate_storage_account`, `tfstate_container`).

3. **Local Azure CLI is logged in** as a user with Owner on the
   subscription:
   ```bash
   az login
   az account set --subscription <id>
   ```

## First apply (one-time, locally)

```bash
cd deploy/terraform

terraform init \
  -backend-config="resource_group_name=<bootstrap.tfstate_resource_group>" \
  -backend-config="storage_account_name=<bootstrap.tfstate_storage_account>" \
  -backend-config="container_name=platform-tfstate" \
  -backend-config="key=aml-compliance.tfstate"

cat > terraform.tfvars <<EOF
env                              = "dev"
owner_email                      = "you@example.com"
github_repo                      = "tomqwu/aml_open_framework"
platform_tfstate_resource_group  = "<from bootstrap>"
platform_tfstate_storage_account = "<from bootstrap>"
platform_tfstate_container       = "platform-tfstate"

# Persistence backend — pick exactly one:
#   Postgres (default, PAYG/EA/MCA subs):
#     enable_postgres = true
#   Cosmos serverless (Sponsorship subs where Postgres is region-locked):
#     enable_postgres = false
#     enable_cosmos   = true
#     # cosmos_database_name = "aml"   # optional, defaults to "aml"

# Optional: pin the app-tier (RG, UAMI, KV, Container Apps) to a
# region different from the platform's primary. See "Co-locating the
# runtime with the DB" below for when to use this. Leave empty to
# inherit the platform location.
#   app_location_override = "canadacentral"
EOF

terraform plan
terraform apply
```

First apply takes ~5 minutes when Postgres is enabled (Flexible Server
provisioning is the slow path). The Cosmos serverless path provisions in
~2 minutes. Subsequent applies are seconds when only the image tag
changed.

## Populate the per-app Key Vault

After the first apply, the framework's API needs a real `JWT-SECRET`.
The Terraform writes a placeholder so the first apply succeeds; replace
it before exposing the API:

```bash
KV=$(terraform output -raw key_vault_name)
az keyvault secret set --vault-name "$KV" --name JWT-SECRET \
  --value "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

# Optional: only needed if you want the GenAI co-pilot's OpenAI backend.
az keyvault secret set --vault-name "$KV" --name OPENAI-API-KEY \
  --value "<your-openai-key>"
```

The `lifecycle.ignore_changes` block on the placeholder secrets means
subsequent `terraform apply` runs won't overwrite operator values.

## Configure GitHub Actions repo variables

The federated identity credentials the landing zone created scope to
`tomqwu/aml_open_framework` on `main`. Set the public variables:

```bash
gh variable set AZURE_CLIENT_ID -b "$(terraform output -raw identity_client_id)"
gh variable set AZURE_TENANT_ID -b "$(terraform output -json github_actions_variables | jq -r .AZURE_TENANT_ID)"
gh variable set AZURE_SUBSCRIPTION_ID -b "$(terraform output -json github_actions_variables | jq -r .AZURE_SUBSCRIPTION_ID)"
gh variable set AZURE_RESOURCE_GROUP -b "$(terraform output -raw resource_group_name)"
gh variable set AZURE_CONTAINER_APP_API -b "$(terraform output -json github_actions_variables | jq -r .AZURE_CONTAINER_APP_API)"
gh variable set AZURE_CONTAINER_APP_DASHBOARD -b "$(terraform output -json github_actions_variables | jq -r .AZURE_CONTAINER_APP_DASHBOARD)"
```

Values are non-secret (just the resource IDs / client IDs); they're
public-by-design so workflows can run without rotating secrets.

## Co-locating the runtime with the DB

By default the per-app RG, UAMI, per-app Key Vault, Container Apps
Environment, and Container Apps all live in the platform's primary
region (typically `eastus`). Two scenarios make a per-app override
useful:

1. **Region-restricted DB.** Azure Sponsorship subscriptions return
   `LocationIsOfferRestricted` on Postgres Flexible Server in most
   US regions; the lifetime free tier (100k vCore-seconds, 32 GiB)
   is offered in `canadacentral`. With Postgres pinned to
   canadacentral but the runtime in eastus, every API → DB query
   crosses the border (~30–50 ms typical). Pinning the runtime to
   canadacentral too keeps the request path intra-region.
2. **Operator / user proximity.** When the operator or end users
   live close to a non-primary region (e.g. Toronto, where
   canadacentral is the closest Azure DC), running the dashboard
   there shaves ~100 ms off interactive latency.

To opt in, set `app_location_override` in `terraform.tfvars`:

```
app_location_override = "canadacentral"
```

The slug must be in the platform's `allowed_locations` policy and is
validated by the upstream module (`^[a-z][a-z0-9]+$` — display names
like `Canada Central` are rejected).

**Switching this on an existing deploy is destructive.** The per-app
RG name encodes the location (`rg-aml-compliance-<env>-<location>`),
so Terraform destroys and recreates the entire RG — UAMI, KV,
Container Apps Environment, both Container Apps, all diagnostic
settings, federated identity credentials, the lot. Specifically:

- The old per-app Key Vault enters 90-day soft-delete with purge
  protection. The same KV name cannot be reused in that window;
  since the LZ rolls a fresh `random_string.kv_suffix` per RG
  creation, this isn't a blocker for the new region but is worth
  noting if you ever want to switch back.
- The new per-app KV needs `JWT-SECRET` re-seeded after the apply
  (Terraform's placeholder has `lifecycle.ignore_changes = [value]`).
- Container Apps revision history is RG-scoped and lost.
- Application Insights traces previously associated with the old
  Container App resources stay queryable in the platform App
  Insights (which lives in the platform region), but they won't be
  associated with the new resources by Azure-resource-ID path.

End-to-end: ~5–10 min downtime during the destroy-recreate cycle.

After the apply, re-seed the secret:

```bash
KV=$(terraform output -raw key_vault_name)
az keyvault secret set --vault-name "$KV" --name JWT-SECRET \
  --value "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

The platform layer (LAW, App Insights, ACR, platform KV, tfstate
Storage) is unaffected — those stay in the platform region per
landing-zone policy.

## Smoke test

```bash
API_URL=$(terraform output -raw api_url)
curl -fsS "${API_URL}/api/v1/health"
# {"status": "ok"}

DASH_URL=$(terraform output -raw dashboard_url)
echo "Open in browser: $DASH_URL"
```

Then walk a `case_id` through Lineage Explorer (page #32) to confirm
the Round-12 lineage chain works end-to-end against the cloud-deployed
dashboard.

## Cost expectations

Idle (no traffic, no engine runs):

| Component | Approx. monthly |
|---|---|
| Container App API (min 1 replica, 0.5 vCPU, 1 GiB) | ~$10 |
| Container App dashboard (min 1 replica) | ~$10 |
| Postgres Flexible Server B1ms (`enable_postgres=true`) | ~$13 (or $0 with the Sponsorship-sub free tier in canadacentral, lifetime of subscription per Azure offer terms) |
| Cosmos DB serverless (`enable_cosmos=true`) | ~$0 idle (no provisioned RU/s — billed per-operation; the AML workload's read/write rate is well under the no-charge floor for a demo deployment) |
| Application Insights ingestion | ~$0 (idle) |
| Per-app Key Vault | ~$0.03 / 10k ops |
| **Total** (Postgres) | **~$33/mo**, or ~$20/mo with the free Postgres tier |
| **Total** (Cosmos) | **~$20/mo** |

Plus the landing zone baseline (~$5/mo for ACR Basic).

Verify with the landing zone's `./scripts/cost-report.sh` after a few
days of usage.

## Subsequent deploys via CI

After the one-time apply + variable-set above, the
`.github/workflows/deploy-azure-landing-zone.yml` pipeline (PR-AZ-6)
handles every subsequent push to `main`:

1. `azure/login@v2` via FIC OIDC.
2. `docker build` + `docker push` to the platform ACR.
3. `terraform plan` → `terraform apply`.
4. `az containerapp update --image ...` to roll the revision.

Local applies still work for one-off changes (e.g., bumping
`enable_dashboard`); the CI just keeps the production env in sync with
the merged main branch.

## Tearing down

```bash
terraform destroy
```

Notes:
- The per-app Key Vault has 90-day soft-delete + purge protection (per
  landing zone CLAUDE.md). After destroy, the vault remains in
  soft-deleted state for 90 days before being permanently purged.
- The Postgres Flexible Server has 7-day backup retention by default;
  destroying the server takes the backups too unless point-in-time
  restore is configured.
- The Cosmos account is destroyed cleanly; serverless containers have
  no provisioned-throughput unwinding to do. Continuous backups are
  off by default — turn them on via `backup` block on
  `azurerm_cosmosdb_account` if point-in-time restore is needed.
- The landing zone's per-app RG is destroyed along with everything in
  it. The platform RG (Log Analytics, App Insights, ACR) survives.
