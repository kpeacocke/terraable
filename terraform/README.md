# Terraform

Terraform content for substrate provisioning and HCP Terraform handoff outputs.

## Substrate modules

| Module | Target | Notes |
|--------|--------|-------|
| `modules/substrate_local` | Local lab / workshop | MVP live path; `backstage` only |
| `modules/substrate_openshift` | Red Hat OpenShift | Phase 2 groundwork; connects to existing cluster |
| `modules/substrate_aws` | Amazon Web Services | Phase 2; provisions VPC + RHEL 9 EC2 instance |
| `modules/substrate_azure` | Microsoft Azure | Phase 2; provisions RG + VNet + RHEL 9 VM |
| `modules/substrate_okd` | OKD (OpenShift community) | Phase 2; connects to existing OKD cluster |

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
