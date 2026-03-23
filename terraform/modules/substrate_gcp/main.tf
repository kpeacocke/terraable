# Scaffold contract module: captures inputs and emits the Terraform-to-Ansible handoff outputs.
# This module does not provision GCP Compute Engine resources directly.
# Phase 2 will add the google provider and compute resource definitions.
# See docs/handoff-contract.md for the contract schema.

locals {
  environment_name = var.environment_name
  api_endpoint     = "https://${var.environment_name}.${var.region}.gcp.local"
}

resource "terraform_data" "environment_contract" {
  input = {
    environment_name = local.environment_name
    portal_impl      = var.portal_impl
    security_profile = var.security_profile
    region           = var.region
    project_id       = var.project_id
  }
}

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = terraform_data.environment_contract.output.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "gcp"
}

output "portal_impl" {
  description = "Selected portal implementation"
  value       = terraform_data.environment_contract.output.portal_impl
}

output "security_profile" {
  description = "Selected security profile"
  value       = terraform_data.environment_contract.output.security_profile
}

output "connection" {
  description = "Connection details consumed by the handoff contract"
  value = {
    ansible_inventory_group = var.ansible_inventory_group
    ssh_user                = var.ssh_user
    ssh_port                = var.ssh_port
    api_endpoint            = local.api_endpoint
  }
}
