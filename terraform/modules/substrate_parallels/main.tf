locals {
  environment_name = var.environment_name
  api_endpoint     = "https://${var.host_system}:443"
}

resource "terraform_data" "environment_contract" {
  input = {
    environment_name = local.environment_name
    portal_impl      = var.portal_impl
    security_profile = var.security_profile
    host_system      = var.host_system
  }
}

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = terraform_data.environment_contract.output.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "parallels"
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
