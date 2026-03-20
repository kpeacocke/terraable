variable "environment_name" {
  description = "Friendly environment name"
  type        = string
}

variable "location" {
  description = "Azure region for substrate resources"
  type        = string
  default     = "australiaeast"
}

variable "resource_group_name" {
  description = "Name of the Azure resource group for substrate resources"
  type        = string
}

variable "portal_impl" {
  description = "Portal implementation selector"
  type        = string
  validation {
    condition     = contains(["rhdh", "backstage"], var.portal_impl)
    error_message = "portal_impl must be either rhdh or backstage."
  }
}

variable "security_profile" {
  description = "Security profile selector"
  type        = string
  validation {
    condition     = contains(["baseline", "strict"], var.security_profile)
    error_message = "security_profile must be baseline or strict."
  }
}

variable "ansible_inventory_group" {
  description = "Ansible inventory group for post-provision actions"
  type        = string
}

variable "ssh_user" {
  description = "SSH user for operational workflows"
  type        = string
  default     = "azureuser"
}

variable "ssh_port" {
  description = "SSH port for operational workflows"
  type        = number
  default     = 22
}

variable "vnet_cidr" {
  description = "Address space for the substrate virtual network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "vm_size" {
  description = "Azure VM size for the substrate node"
  type        = string
  default     = "Standard_B2s"
}

variable "ssh_public_key" {
  description = "SSH public key content for admin access to the substrate VM"
  type        = string
}

variable "allowed_source_prefix" {
  description = "Source IP prefix permitted for SSH, HTTP, and HTTPS inbound rules. Restrict to operator IP ranges in non-demo environments."
  type        = string
  default     = "*"
}
