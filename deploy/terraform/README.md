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
