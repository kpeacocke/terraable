variable "environment_name" {
  description = "Friendly environment name"
  type        = string
}

variable "local_host" {
  description = "Hostname or IP address of the local workshop target"
  type        = string
  default     = "localhost"
}

variable "portal_impl" {
  description = "Portal implementation selector. Only backstage is supported for local-lab targets."
  type        = string
  validation {
    condition     = var.portal_impl == "backstage"
    error_message = "portal_impl must be backstage for local-lab targets. rhdh requires an OpenShift substrate."
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
  default     = "local_lab"
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
