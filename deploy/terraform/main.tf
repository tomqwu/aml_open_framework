# Round 16 PR-AZ-5 — AML compliance framework deployment on top of the
# landing zone at https://github.com/tomqwu/cloud_landing_zone_for_ai_coding.
#
# Constraints inherited from the landing zone CLAUDE.md:
#   - Compute: Container Apps only (no AKS, no VMs)
#   - DB: Postgres Flexible Server B1ms with Entra ID auth
#   - Diagnostics → platform Log Analytics workspace (mandatory)
#   - Secrets in per-app Key Vault
#   - HTTPS-only + TLS 1.2
#   - Tags: app, env, owner (from module.onboard.tags)

# ---------------------------------------------------------------------------
# 1. Onboard with the landing zone — vends RG, UAMI, per-app Key Vault,
#    federated identity credentials, AcrPull + Metrics Publisher RBAC.
# ---------------------------------------------------------------------------

module "onboard" {
  # Private repo — uses SSH auth via the operator's local SSH key.
  # In CI, the deploy workflow checks out the landing zone repo
  # explicitly via actions/checkout with an SSH deploy key, then
  # passes a local file path here via -var (see workflow comments).
  source = "git::ssh://git@github.com/tomqwu/cloud_landing_zone_for_ai_coding.git//modules/app-onboard?ref=main"

  app_name        = "aml-compliance"
  env             = var.env
  github_repo     = var.github_repo
  github_branches = var.github_branches
  owner_email     = var.owner_email
  enable_acr_pull = true

  # Place per-app resources (RG, UAMI, KV, Container Apps, Postgres,
  # Cosmos) in canadacentral by default — Toronto-based operator and
  # the Sponsorship Postgres free tier is offered in canadacentral.
  # Platform-shared resources (LAW, App Insights, ACR) stay in the
  # platform region. The default is set in variables.tf; flip via
  # tfvars or `-var` for a different region.
  location_override = var.app_location_override

  platform_outputs = {
    subscription_id            = data.terraform_remote_state.platform.outputs.subscription_id
    tenant_id                  = data.terraform_remote_state.platform.outputs.tenant_id
    location                   = data.terraform_remote_state.platform.outputs.location
    naming_prefix              = data.terraform_remote_state.platform.outputs.naming_prefix
    log_analytics_workspace_id = data.terraform_remote_state.platform.outputs.log_analytics_workspace_id
    appinsights_id             = data.terraform_remote_state.platform.outputs.appinsights_id
    acr_login_server           = data.terraform_remote_state.platform.outputs.acr_login_server
    acr_resource_id            = data.terraform_remote_state.platform.outputs.acr_resource_id
  }
}

# ---------------------------------------------------------------------------
# 1b. Persistence-backend mutex.
#     enable_postgres and enable_cosmos must not both be true: the app
#     wires DATABASE_URL or COSMOS_ENDPOINT, never both, and provisioning
#     both server-side leaks an idle account that nothing reads. Matches
#     the equivalent fail-fast in deploy/helm/templates/api-deployment.yaml.
#     A precondition on the Postgres resource itself wouldn't fire when
#     enable_postgres=false, so guard via terraform_data which always plans.
# ---------------------------------------------------------------------------

resource "terraform_data" "db_backend_mutex" {
  lifecycle {
    precondition {
      condition     = !(var.enable_postgres && var.enable_cosmos)
      error_message = "enable_postgres and enable_cosmos are mutually exclusive. Pick one persistence backend (or set both to false for SQLite)."
    }
  }
}

# ---------------------------------------------------------------------------
# 2. Postgres Flexible Server (B1ms, Entra-ID-only auth).
#    Random suffix because Postgres FQDNs need to be globally unique.
# ---------------------------------------------------------------------------

resource "random_string" "pg_suffix" {
  count   = var.enable_postgres ? 1 : 0
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_postgresql_flexible_server" "aml" {
  count               = var.enable_postgres ? 1 : 0
  name                = "psql-aml-${var.env}-${random_string.pg_suffix[0].result}"
  resource_group_name = module.onboard.resource_group_name
  # Allow override when Sponsorship subscriptions lock the platform's
  # default region (eastus is commonly restricted for Postgres).
  location = var.postgres_location != "" ? var.postgres_location : module.onboard.location

  version                       = "16"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  zone                          = "1"
  public_network_access_enabled = true
  # Per landing zone CLAUDE.md: Entra ID auth only — no password auth.
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  tags = module.onboard.tags
}

# Make the app's UAMI the Azure AD admin so the Container App can
# authenticate to Postgres via DefaultAzureCredential.
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "aml_uami" {
  count               = var.enable_postgres ? 1 : 0
  server_name         = azurerm_postgresql_flexible_server.aml[0].name
  resource_group_name = module.onboard.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = module.onboard.identity_principal_id
  principal_name      = "aml-compliance-${var.env}-uami"
  principal_type      = "ServicePrincipal"
}

# Allow the Container Apps environment to reach Postgres. The landing
# zone forbids private VNets; Container Apps egress IPs aren't
# predictable, so allow Azure-internal traffic via the firewall rule.
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  count            = var.enable_postgres ? 1 : 0
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.aml[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "aml" {
  count     = var.enable_postgres ? 1 : 0
  name      = "aml"
  server_id = azurerm_postgresql_flexible_server.aml[0].id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# ---------------------------------------------------------------------------
# 2b. Cosmos DB serverless (alternative persistence backend).
#    Used when enable_cosmos=true — typically on Sponsorship subs that
#    block Postgres Flexible Server in every available region. The Python
#    layer (src/aml_framework/api/db.py) selects Cosmos over
#    Postgres/SQLite when COSMOS_ENDPOINT is set.
#    Free-tier-friendly: serverless billing has no idle compute charge.
# ---------------------------------------------------------------------------

resource "random_string" "cosmos_suffix" {
  count   = var.enable_cosmos ? 1 : 0
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_cosmosdb_account" "aml" {
  count               = var.enable_cosmos ? 1 : 0
  name                = "cosmos-aml-${var.env}-${random_string.cosmos_suffix[0].result}"
  resource_group_name = module.onboard.resource_group_name
  location            = module.onboard.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  # Serverless mode: no provisioned RU/s, billed per-operation. Idle ≈ $0.
  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = module.onboard.location
    failover_priority = 0
  }

  # AAD-only access — no key-based auth from the app side. The UAMI gets
  # data plane access via the SQL role assignment below.
  local_authentication_disabled = true
  public_network_access_enabled = true

  tags = module.onboard.tags
}

resource "azurerm_cosmosdb_sql_database" "aml" {
  count               = var.enable_cosmos ? 1 : 0
  name                = var.cosmos_database_name
  resource_group_name = module.onboard.resource_group_name
  account_name        = azurerm_cosmosdb_account.aml[0].name
}

# 4 containers matching the schema in src/aml_framework/api/db.py.
# Partition key /tenant_id everywhere so tenant-scoped queries stay
# single-partition. Document `id` shape: run_id, run_id:rule_id,
# run_id, tenant_id:spec_hash respectively.
locals {
  cosmos_containers = var.enable_cosmos ? toset([
    "runs",
    "run_alerts",
    "run_metrics",
    "spec_versions",
  ]) : toset([])
}

resource "azurerm_cosmosdb_sql_container" "aml" {
  for_each              = local.cosmos_containers
  name                  = each.value
  resource_group_name   = module.onboard.resource_group_name
  account_name          = azurerm_cosmosdb_account.aml[0].name
  database_name         = azurerm_cosmosdb_sql_database.aml[0].name
  partition_key_paths   = ["/tenant_id"]
  partition_key_version = 2
}

# Grant the app's UAMI the built-in "Cosmos DB Built-in Data Contributor"
# role on the account. ID 00000000-0000-0000-0000-000000000002 is fixed
# for that built-in role; documented in
# https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access
resource "azurerm_cosmosdb_sql_role_assignment" "aml_uami" {
  count               = var.enable_cosmos ? 1 : 0
  resource_group_name = module.onboard.resource_group_name
  account_name        = azurerm_cosmosdb_account.aml[0].name
  role_definition_id  = "${azurerm_cosmosdb_account.aml[0].id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = module.onboard.identity_principal_id
  scope               = azurerm_cosmosdb_account.aml[0].id
}

# ---------------------------------------------------------------------------
# 3. Container Apps Environment — single env shared by API + dashboard.
#    Linked to platform Log Analytics workspace per CLAUDE.md mandate.
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "aml" {
  name                       = "cae-aml-${var.env}"
  resource_group_name        = module.onboard.resource_group_name
  location                   = module.onboard.location
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  tags = module.onboard.tags
}

# ---------------------------------------------------------------------------
# 4. Container App: API (FastAPI on uvicorn, port 8000).
#    Image pulled from the platform ACR via UAMI (AcrPull was granted by
#    the app-onboard module).
# ---------------------------------------------------------------------------

locals {
  acr_image_api       = "${module.onboard.acr_login_server}/aml-framework:${var.image_tag}"
  acr_image_dashboard = "${module.onboard.acr_login_server}/aml-framework:${var.image_tag}"
  appinsights_conn    = data.terraform_remote_state.platform.outputs.appinsights_connection_string
}

resource "azurerm_container_app" "api" {
  name                         = "ca-aml-api-${var.env}"
  resource_group_name          = module.onboard.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.aml.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [module.onboard.identity_id]
  }

  registry {
    server   = module.onboard.acr_login_server
    identity = module.onboard.identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3
    container {
      name   = "api"
      image  = local.acr_image_api
      cpu    = 0.5
      memory = "1.0Gi"
      command = [
        "python", "-m", "uvicorn",
        "aml_framework.api.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
      ]
      env {
        name  = "AML_ENV"
        value = var.env
      }
      env {
        name  = "AZURE_KEY_VAULT_NAME"
        value = split(".", replace(module.onboard.key_vault_uri, "https://", ""))[0]
      }
      env {
        name  = "API_DATA_ROOTS"
        value = "data"
      }
      env {
        name  = "API_UPLOAD_ROOT"
        value = "data/uploads"
      }
      env {
        name  = "API_ARTIFACT_ROOT"
        value = "data/api-artifacts"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-conn"
      }
      dynamic "env" {
        for_each = var.enable_postgres ? [1] : []
        content {
          name        = "DATABASE_URL"
          secret_name = "database-url"
        }
      }
      dynamic "env" {
        for_each = var.enable_cosmos ? [1] : []
        content {
          name  = "COSMOS_ENDPOINT"
          value = azurerm_cosmosdb_account.aml[0].endpoint
        }
      }
      dynamic "env" {
        for_each = var.enable_cosmos ? [1] : []
        content {
          name  = "COSMOS_DATABASE"
          value = azurerm_cosmosdb_sql_database.aml[0].name
        }
      }
    }
  }

  secret {
    name  = "appinsights-conn"
    value = local.appinsights_conn
  }

  dynamic "secret" {
    for_each = var.enable_postgres ? [1] : []
    content {
      name = "database-url"
      # Container Apps reads the secret value verbatim. The Python code
      # calls SECRETS.get("DATABASE_URL") which falls through to env.
      # Format uses the UAMI principal_id for Entra ID auth.
      value = "postgresql://${module.onboard.identity_principal_id}@${azurerm_postgresql_flexible_server.aml[0].fqdn}:5432/aml?sslmode=require&authentication=azure_ad"
    }
  }

  tags = module.onboard.tags
}

# ---------------------------------------------------------------------------
# 5. Container App: dashboard (Streamlit on port 8501).
#    Optional via var.enable_dashboard.
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "dashboard" {
  count = var.enable_dashboard ? 1 : 0

  name                         = "ca-aml-dashboard-${var.env}"
  resource_group_name          = module.onboard.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.aml.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [module.onboard.identity_id]
  }

  registry {
    server   = module.onboard.acr_login_server
    identity = module.onboard.identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2
    container {
      name   = "dashboard"
      image  = local.acr_image_dashboard
      cpu    = 0.5
      memory = "1.0Gi"
      command = [
        "python", "-m", "streamlit", "run",
        "src/aml_framework/dashboard/app.py",
        "--server.port", "8501",
        "--server.headless", "true",
        "--", var.spec_path, "42",
      ]
      env {
        name  = "AZURE_KEY_VAULT_NAME"
        value = split(".", replace(module.onboard.key_vault_uri, "https://", ""))[0]
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-conn"
      }
      dynamic "env" {
        for_each = var.enable_cosmos ? [1] : []
        content {
          name  = "COSMOS_ENDPOINT"
          value = azurerm_cosmosdb_account.aml[0].endpoint
        }
      }
      dynamic "env" {
        for_each = var.enable_cosmos ? [1] : []
        content {
          name  = "COSMOS_DATABASE"
          value = azurerm_cosmosdb_sql_database.aml[0].name
        }
      }
    }
  }

  secret {
    name  = "appinsights-conn"
    value = local.appinsights_conn
  }

  tags = module.onboard.tags
}

# ---------------------------------------------------------------------------
# 6. Pre-seed the per-app Key Vault with placeholder secrets the API
#    expects. Operators populate the real values via:
#        az keyvault secret set --vault-name <kv> --name JWT-SECRET --value ...
# ---------------------------------------------------------------------------

# Grant the Terraform operator (the user running `terraform apply` —
# `data.azurerm_client_config.current.object_id`) Key Vault Secrets
# Officer on the per-app KV. The app-onboard module gives the app's
# UAMI Secrets User; the operator needs Officer to seed the
# placeholder secrets below.
resource "azurerm_role_assignment" "operator_kv_secrets_officer" {
  scope                = module.onboard.key_vault_id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "jwt_secret_placeholder" {
  name         = "JWT-SECRET"
  value        = "REPLACE-WITH-32-PLUS-BYTE-RANDOM-VALUE"
  key_vault_id = module.onboard.key_vault_id
  content_type = "text/plain"

  depends_on = [azurerm_role_assignment.operator_kv_secrets_officer]

  lifecycle {
    # Don't overwrite operator-supplied real values on subsequent applies.
    ignore_changes = [value]
  }
}

resource "azurerm_key_vault_secret" "openai_api_key_placeholder" {
  name         = "OPENAI-API-KEY"
  value        = "REPLACE-WITH-OPENAI-KEY-OR-LEAVE-FOR-TEMPLATE-BACKEND"
  key_vault_id = module.onboard.key_vault_id
  content_type = "text/plain"

  depends_on = [azurerm_role_assignment.operator_kv_secrets_officer]

  lifecycle {
    ignore_changes = [value]
  }
}

# ---------------------------------------------------------------------------
# 7. Diagnostic settings — every resource sends to the platform LAW.
#    Mandatory per landing zone CLAUDE.md.
# ---------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "api" {
  name                       = "diag-aml-api"
  target_resource_id         = azurerm_container_app.api.id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  # Container Apps doesn't expose category_group=allLogs; metrics
  # alone cover the platform-LAW diagnostics requirement.
  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "dashboard" {
  count                      = var.enable_dashboard ? 1 : 0
  name                       = "diag-aml-dashboard"
  target_resource_id         = azurerm_container_app.dashboard[0].id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "postgres" {
  count                      = var.enable_postgres ? 1 : 0
  name                       = "diag-aml-postgres"
  target_resource_id         = azurerm_postgresql_flexible_server.aml[0].id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  enabled_log {
    category = "PostgreSQLLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "cosmos" {
  count                      = var.enable_cosmos ? 1 : 0
  name                       = "diag-aml-cosmos"
  target_resource_id         = azurerm_cosmosdb_account.aml[0].id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  # Cosmos exposes data-plane logs (DataPlaneRequests, QueryRuntimeStatistics,
  # PartitionKeyStatistics) and control-plane logs. Enabling the
  # category_group "audit" is the minimum the landing zone CLAUDE.md
  # requires for "every resource ships logs to platform LAW"; richer
  # categories are available if the operator needs query-level tracing.
  enabled_log {
    category_group = "audit"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
