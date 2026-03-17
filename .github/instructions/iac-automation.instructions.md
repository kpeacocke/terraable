---
description: Use when editing Terraform, Ansible, workflow, or automation-related files for terraable.
applyTo: "**/*.{tf,tfvars,hcl,yml,yaml,json,sh,ps1}"
---

# IaC and automation standards

- Preserve strict separation:
- Terraform for provisioning and substrate lifecycle.
- Ansible for operational hardening, scan, drift response, and remediation.
- Define explicit handoff payloads between Terraform outputs and Ansible inputs.

## Reliability rules
- Ensure workflows are deterministic and idempotent where practical.
- Capture actionable status and evidence outputs for each major step.
- Surface errors with enough context for operators to remediate quickly.

## Security rules
- Use least-privilege assumptions for cloud and platform operations.
- Never hardcode credentials or access tokens.
- Validate externally sourced input before execution.

## Testing and validation
- Add validation checks for changed contracts and interfaces.
- Include at least one failure-path test or verification step for new automation logic.
- Prefer incremental changes that can be demonstrated safely in workshop and offline/mock contexts.

## Design guidance
- Keep provider-specific logic in adapters, not shared orchestration paths.
- Avoid implicit magic values; prefer explicit configuration with safe defaults.
- Document any behavioural impact on compliance, drift detection, or remediation flows.
