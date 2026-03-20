# MVP Demo Runbook

## Purpose and Scope
This runbook defines the step-by-step execution path for the MVP demo narrative.
It covers selector setup, baseline and compliance actions, controlled drift injection, remediation, and evidence review.
It applies to showcase, lab, and offline/mock execution paths used by contributors and presenters.

## Prerequisites
- Python 3.11+, Terraform 1.5+, and Ansible 10 are available.
- Repository checks pass locally.
- Target credentials are configured through environment variables.

## Procedure Inputs
- Target selector: `openshift`, `aws`, or `local-lab`
- Portal selector: `rhdh` or `backstage`
- Security profile: `baseline` or `strict`
- EDA toggle: `enabled` or `disabled` (MVP: informational/UI-only, does not change the Terraform-to-Ansible handoff or Python runtime models; used to narrate the future EDA path planned for Phase 2)

## Procedure
1. Start with control-plane selectors and create environment request.
2. Show Terraform stage evidence and run identifier.
3. Trigger baseline application.
4. Trigger compliance scan and show pass state.
5. Inject SSH drift (`PermitRootLogin yes`) and re-run scan.
6. Trigger remediation and verify recovered scan status.
7. Highlight evidence panel timeline for all actions.

## Expected Outputs
- Baseline and remediation actions return success status.
- Compliance scan fails during injected drift and passes post-remediation.
- Evidence panel reflects every action with status and detail.

## Recovery Steps
- Terraform run unavailable: switch to offline/mock mode for narrative continuity.
- Scan output missing: rerun scan action and verify inventory connectivity.
- Remediation fails: execute remediation playbook manually and rerun scan.
