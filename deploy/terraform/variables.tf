# Round 16 PR-AZ-5 — Inputs to the AML deployment module.
# All required inputs live here. Defaults match the landing zone's
# preferred shape (B1ms Postgres, eastus, dev env).

variable "env" {
  description = "Environment name. Must be one of: dev, staging, prod, test (landing zone constraint)."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod", "test"], var.env)
    error_message = "env must be one of: dev, staging, prod, test."
  }
}

variable "owner_email" {
  description = "Tag value applied to every resource and propagated through the landing zone's app-onboard module."
  type        = string
}

variable "github_repo" {
  description = "GitHub repo for federated identity credentials. The landing zone creates FICs scoped to this repo + the branches below."
  type        = string
  default     = "tomqwu/aml_open_framework"
}

variable "github_branches" {
  description = "Branches that may run the deploy workflow."
  type        = list(string)
  default     = ["main"]
}

variable "image_tag" {
  description = "ACR image tag for the API + dashboard. Default 'latest'; in CI override with the commit SHA."
  type        = string
  default     = "latest"
}

variable "enable_dashboard" {
  description = "Provision the Streamlit dashboard Container App alongside the API. Set false for API-only deployments."
  type        = bool
  default     = true
}

variable "spec_path" {
  description = "Path to the AML spec inside the container image. Default ships the bundled Canadian Schedule I bank example."
  type        = string
  default     = "examples/canadian_schedule_i_bank/aml.yaml"
}

variable "postgres_admin_login" {
  description = "Entra ID principal that owns the Postgres server (Azure AD admin). Typically the same managed identity used by CI."
  type        = string
  default     = ""
}

variable "postgres_location" {
  description = "Override location for the Postgres Flexible Server. Some Sponsorship subscriptions restrict Postgres provisioning in certain regions (eastus is commonly locked); set this to a working region (e.g. eastus2, westus2). Empty string falls back to the app RG's location."
  type        = string
  default     = ""
}

variable "enable_postgres" {
  description = "Provision Postgres Flexible Server. Set false to deploy Container Apps with SQLite fallback (in-container, non-persistent — fine for demos). Useful when Sponsorship subscriptions lock the platform's allowed region."
  type        = bool
  default     = true
}

variable "enable_cosmos" {
  description = "Provision a Cosmos DB serverless account + database + 4 containers (runs, run_alerts, run_metrics, spec_versions) and inject COSMOS_ENDPOINT/COSMOS_DATABASE into the Container Apps. The Python layer (src/aml_framework/api/db.py) selects Cosmos over Postgres/SQLite when COSMOS_ENDPOINT is set. Use as an alternative to Postgres on Sponsorship subs that block Postgres Flexible Server in every available region."
  type        = bool
  default     = false
}

variable "cosmos_database_name" {
  description = "Cosmos DB database name. Default 'aml' matches the COSMOS_DATABASE Python default."
  type        = string
  default     = "aml"
}

# --- Landing zone tfstate location -----------------------------------------
# These three variables tell the data source where to read the
# landing zone's platform outputs. Pull them from
# https://github.com/tomqwu/cloud_landing_zone_for_ai_coding bootstrap
# outputs or from `gh variable list` on the landing zone repo.

variable "platform_tfstate_resource_group" {
  description = "Resource group holding the landing zone's tfstate Storage Account."
  type        = string
}

variable "platform_tfstate_storage_account" {
  description = "Landing zone's tfstate Storage Account name (globally unique)."
  type        = string
}

variable "platform_tfstate_container" {
  description = "Landing zone's tfstate container name. Default 'tfstate'."
  type        = string
  default     = "tfstate"
}
