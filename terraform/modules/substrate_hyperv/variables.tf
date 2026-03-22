variable "environment_name" {
  description = "Friendly environment name"
  type        = string
}

variable "host_system" {
  description = "Hyper-V host system identifier"
  type        = string
  default     = "hyperv-host.local"
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
  default     = "hyperv_hosts"
}

variable "ssh_user" {
  description = "SSH user for operational workflows"
  type        = string
  default     = "lab"
}

variable "ssh_port" {
  description = "SSH port for operational workflows"
  type        = number
  default     = 22
}
