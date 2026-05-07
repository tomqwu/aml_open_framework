# Round 16 PR-AZ-5 — outputs the deployment publishes.
# Consumed by the GitHub Actions deploy pipeline (PR-AZ-6) and by
# operators who need to populate Key Vault, smoke-test the URL, etc.

output "resource_group_name" {
  description = "Per-app Resource Group vended by the landing zone."
  value       = module.onboard.resource_group_name
}

output "key_vault_name" {
  description = "Per-app Key Vault. Populate JWT-SECRET / OPENAI-API-KEY here after first apply."
  value       = split(".", replace(module.onboard.key_vault_uri, "https://", ""))[0]
}

output "key_vault_uri" {
  description = "Full HTTPS endpoint for the per-app Key Vault."
  value       = module.onboard.key_vault_uri
}

output "identity_client_id" {
  description = "User-assigned managed identity client_id. Set as AZURE_CLIENT_ID GitHub repo variable."
  value       = module.onboard.identity_client_id
}

output "api_url" {
  description = "Public HTTPS URL for the API Container App."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "dashboard_url" {
  description = "Public HTTPS URL for the dashboard Container App. Null when enable_dashboard=false."
  value       = var.enable_dashboard ? "https://${azurerm_container_app.dashboard[0].ingress[0].fqdn}" : null
}

output "postgres_fqdn" {
  description = "Postgres Flexible Server FQDN. Use with the UAMI client_id for Entra ID auth."
  value       = azurerm_postgresql_flexible_server.aml.fqdn
}

output "github_actions_variables" {
  description = "Set these as GitHub repo Variables (not Secrets). Pass to the deploy workflow."
  value = merge(module.onboard.github_actions_variables, {
    AZURE_CONTAINER_APP_API       = azurerm_container_app.api.name
    AZURE_CONTAINER_APP_DASHBOARD = var.enable_dashboard ? azurerm_container_app.dashboard[0].name : ""
  })
}
