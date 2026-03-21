terraform {
  required_version = ">= 1.9.0"
}

module "substrate_local" {
  source = "../../../terraform/modules/substrate_local"

  environment_name = var.environment_name
  portal_impl      = var.portal_impl
  security_profile = var.security_profile
  local_host       = var.local_host
}

variable "environment_name" {
  type = string
}

variable "portal_impl" {
  type = string
}

variable "security_profile" {
  type = string
}

variable "local_host" {
  type    = string
  default = "localhost"
}

output "environment_name" {
  value = module.substrate_local.environment_name
}

output "target_platform" {
  value = module.substrate_local.target_platform
}

output "portal_impl" {
  value = module.substrate_local.portal_impl
}

output "security_profile" {
  value = module.substrate_local.security_profile
}

output "connection" {
  value = module.substrate_local.connection
}
