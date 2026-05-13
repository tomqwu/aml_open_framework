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

variable "app_location_override" {
  description = "Canonical Azure slug (e.g. 'canadacentral', 'westus2') passed through to the landing zone's app-onboard module. Places the per-app RG, UAMI, per-app Key Vault, Container Apps Environment, Container Apps, and Postgres in this region. Default 'canadacentral' matches the current landing zone deployment (Toronto-based ops, Sponsorship Postgres free tier offered there). Set '' to inherit the platform location, or any other slug in the platform's allowed_locations policy. Validated by the upstream module against ^[a-z][a-z0-9]+$. This is a one-time per-deployment choice — the per-app RG name encodes the location, so changing it on an existing deploy triggers a destroy/recreate of the per-app stack and the old per-app Key Vault enters 90-day soft-delete."
  type        = string
  default     = "canadacentral"
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

# --- GenAI Assistant backend ----------------------------------------------
# These env vars route the dashboard's GenAI co-pilot through one of the
# four backends in src/aml_framework/assistant/. The default 'template'
# uses no LLM (canned scaffolding). Set 'ollama' + AML_OLLAMA_URL to
# https://ollama.com/api/chat to route through Ollama Cloud — the
# OLLAMA-API-KEY secret is pre-seeded in the per-app Key Vault; the
# Python `SECRETS.get("OLLAMA_API_KEY")` path fetches it at runtime.

variable "ai_backend" {
  description = "AML_AI_BACKEND env value. One of: template, ollama, openai, azure_openai. Defaults to template (no LLM)."
  type        = string
  default     = "template"
  validation {
    condition     = contains(["template", "ollama", "openai", "azure_openai"], var.ai_backend)
    error_message = "ai_backend must be one of: template, ollama, openai, azure_openai."
  }
}

variable "ollama_url" {
  description = "AML_OLLAMA_URL env value. Set to https://ollama.com/api/chat for Ollama Cloud, or leave at localhost for an in-cluster Ollama daemon (not provisioned by this module)."
  type        = string
  default     = "https://ollama.com/api/chat"
}

variable "ollama_model" {
  description = "AML_OLLAMA_MODEL env value. Pick from https://ollama.com/library when using Ollama Cloud. Default 'gpt-oss:120b' matches the docs.ollama.com/cloud example; flip to a DeepSeek variant or other free-tier model as available."
  type        = string
  default     = "gpt-oss:120b"
}
