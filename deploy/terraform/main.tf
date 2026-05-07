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
  source = "git::https://github.com/tomqwu/cloud_landing_zone_for_ai_coding.git//modules/app-onboard?ref=main"

  app_name        = "aml-compliance"
  env             = var.env
  github_repo     = var.github_repo
  github_branches = var.github_branches
  owner_email     = var.owner_email
  enable_acr_pull = true

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
# 2. Postgres Flexible Server (B1ms, Entra-ID-only auth).
#    Random suffix because Postgres FQDNs need to be globally unique.
# ---------------------------------------------------------------------------

resource "random_string" "pg_suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_postgresql_flexible_server" "aml" {
  name                = "psql-aml-${var.env}-${random_string.pg_suffix.result}"
  resource_group_name = module.onboard.resource_group_name
  location            = module.onboard.location

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
  server_name         = azurerm_postgresql_flexible_server.aml.name
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
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.aml.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "aml" {
  name      = "aml"
  server_id = azurerm_postgresql_flexible_server.aml.id
  collation = "en_US.utf8"
  charset   = "UTF8"
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
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  secret {
    name  = "appinsights-conn"
    value = local.appinsights_conn
  }

  secret {
    name = "database-url"
    # Container Apps reads the secret value verbatim. The Python code
    # calls SECRETS.get("DATABASE_URL") which falls through to env.
    # Format uses the UAMI client_id for Entra ID auth.
    value = "postgresql://${module.onboard.identity_principal_id}@${azurerm_postgresql_flexible_server.aml.fqdn}:5432/aml?sslmode=require&authentication=azure_ad"
  }

  tags = module.onboard.tags

  depends_on = [
    azurerm_postgresql_flexible_server_active_directory_administrator.aml_uami,
  ]
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

resource "azurerm_key_vault_secret" "jwt_secret_placeholder" {
  name         = "JWT-SECRET"
  value        = "REPLACE-WITH-32-PLUS-BYTE-RANDOM-VALUE"
  key_vault_id = module.onboard.key_vault_id
  content_type = "text/plain"

  lifecycle {
    # Don't overwrite operator-supplied real values on subsequent applies.
    ignore_changes = [value, version]
  }
}

resource "azurerm_key_vault_secret" "openai_api_key_placeholder" {
  name         = "OPENAI-API-KEY"
  value        = "REPLACE-WITH-OPENAI-KEY-OR-LEAVE-FOR-TEMPLATE-BACKEND"
  key_vault_id = module.onboard.key_vault_id
  content_type = "text/plain"

  lifecycle {
    ignore_changes = [value, version]
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

  enabled_log {
    category_group = "allLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}

resource "azurerm_monitor_diagnostic_setting" "dashboard" {
  count                      = var.enable_dashboard ? 1 : 0
  name                       = "diag-aml-dashboard"
  target_resource_id         = azurerm_container_app.dashboard[0].id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}

resource "azurerm_monitor_diagnostic_setting" "postgres" {
  name                       = "diag-aml-postgres"
  target_resource_id         = azurerm_postgresql_flexible_server.aml.id
  log_analytics_workspace_id = module.onboard.log_analytics_workspace_id

  enabled_log {
    category = "PostgreSQLLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}
