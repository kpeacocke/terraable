terraform {
  required_version = ">= 1.5.0"
}

locals {
  environment_name = var.environment_name
  api_endpoint     = "https://api.${var.cluster_name}.${var.base_domain}:6443"
}

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = local.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "openshift"
}

output "portal_impl" {
  description = "Selected portal implementation"
  value       = var.portal_impl
}

output "security_profile" {
  description = "Selected security profile"
  value       = var.security_profile
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
