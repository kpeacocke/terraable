locals {
  environment_name = var.environment_name
  # API endpoint placeholder — resolved from provisioned EKS or EC2 resources at runtime.
  api_endpoint = "https://${var.environment_name}.${var.aws_region}.amazonaws.com"
}

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = local.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "aws"
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
