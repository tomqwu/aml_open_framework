# Round 16 PR-AZ-5 — Terraform deployment module for the AML
# framework, consuming the landing zone at
# https://github.com/tomqwu/cloud_landing_zone_for_ai_coding.
#
# Backend: shared tfstate Storage Account in the landing zone's
# bootstrap RG. Use the `tfstate_storage_account` + `tfstate_container`
# outputs from the landing zone's `bootstrap/` apply, then
# `terraform init -backend-config="storage_account_name=..."` to bind.
#
# Auth: `use_oidc = true` — locally via `az login`, in CI via the
# federated-identity credential the landing zone's `app-onboard`
# module creates for `tomqwu/aml_open_framework`.

terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    # Resource group, storage account, and container come from the
    # landing zone's `bootstrap/` outputs. Pass via -backend-config:
    #   terraform init \
    #     -backend-config="resource_group_name=<from bootstrap>" \
    #     -backend-config="storage_account_name=<from bootstrap>" \
    #     -backend-config="container_name=<from bootstrap>" \
    #     -backend-config="key=aml-compliance.tfstate"
    use_oidc         = true
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {
    key_vault {
      # Per landing zone CLAUDE.md: 90-day retention + purge protection.
      # Don't auto-purge soft-deleted vaults on destroy.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      # Don't fail terraform destroy when resources still exist;
      # the platform's tag policy may keep diagnostic settings around.
      prevent_deletion_if_contains_resources = false
    }
  }
  use_oidc = true
}

# Read platform outputs (Log Analytics workspace ID, App Insights
# connection string, ACR login server) from the landing zone's
# `platform/` tfstate. The data source pattern is the contract the
# landing zone publishes for app onboarding.
data "terraform_remote_state" "platform" {
  backend = "azurerm"
  config = {
    resource_group_name  = var.platform_tfstate_resource_group
    storage_account_name = var.platform_tfstate_storage_account
    container_name       = var.platform_tfstate_container
    key                  = "platform.tfstate"
    use_oidc             = true
    use_azuread_auth     = true
  }
}

data "azurerm_client_config" "current" {}
