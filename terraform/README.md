# Terraform

Terraform content for substrate provisioning and HCP Terraform handoff outputs.

## Substrate modules

| Module | Target | Notes |
| -------- | -------- | ------- |
| `modules/substrate_local` | Local lab / workshop | MVP live path; `rhdh` and `backstage` |
| `modules/substrate_openshift` | Red Hat OpenShift | Phase 2 groundwork; connects to existing cluster |
| `modules/substrate_aws` | Amazon Web Services | Phase 2; provisions VPC + RHEL 9 EC2 instance |
| `modules/substrate_azure` | Microsoft Azure | Phase 2; provisions RG + VNet + RHEL 9 VM |
| `modules/substrate_okd` | OKD (OpenShift community) | Phase 2; connects to existing OKD cluster |
| `modules/substrate_gcp` | Google Cloud Platform | Phase 3 scaffold; emits handoff-compatible contract outputs |
| `modules/substrate_vmware` | VMware local substrate | Phase 3 local target scaffold |
| `modules/substrate_parallels` | Parallels local substrate | Phase 3 local target scaffold |
| `modules/substrate_hyperv` | Hyper-V local substrate | Phase 3 local target scaffold |

> **Lock files**: Terraform provider lock files (`.terraform.lock.hcl`) are not committed for the Phase 3 scaffold modules (`substrate_gcp`, `substrate_vmware`, `substrate_parallels`, `substrate_hyperv`) because they do not yet define provider blocks. Lock files will be added in Phase 2 when provider and resource definitions are wired in.

## Contract outputs

All modules emit a consistent set of outputs consumed by the Terraform-to-Ansible handoff contract. See [`docs/handoff-contract.md`](../docs/handoff-contract.md) for the full schema.

Required outputs per module:

```hcl
output "environment_name"  { ... }
output "target_platform"   { ... }
output "portal_impl"       { ... }
output "security_profile"  { ... }
output "connection"        {
  value = {
    ansible_inventory_group = ...
    ssh_user                = ...
    ssh_port                = ...
    api_endpoint            = ...
  }
}
```

## Adding a new module

1. Create `modules/substrate_<name>/` with `main.tf`, `variables.tf`, and `versions.tf`.
2. Emit all required outputs listed above.
3. Add the target name to `TargetPlatform` in `terraable/contract.py`.
4. Update this README.
