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

## Troubleshooting and Recovery

- Auth or token errors when triggering actions:
  - Confirm you are logged into the control-plane UI and any required token environment variables (for example, `DEMO_CONTROL_PLANE_TOKEN`) are set and not expired.
  - Re-run a simple read-only action (such as listing runs) to confirm the session is valid before starting the full demo path.

- Inventory connectivity issues during scan or remediation:
  - Check that the inventory synchronisation has completed successfully in AAP/AWX or the chosen automation controller.
  - Validate that demo target hosts are reachable (for example, SSH or HTTPS) from the automation controller.
  - If connectivity still fails, switch to offline/mock mode and narrate the expected scan and remediation behaviour.

- Scan output missing or empty:
  - Confirm the scan job completed successfully in the automation controller and did not exit early with an error.
  - Check the configured scan output location or evidence/artefact panel in the control-plane UI.
  - In offline/mock mode, ensure the bundled sample scan results are selected and visible in the evidence panel.

- Terraform run unavailable: switch to offline/mock mode for narrative continuity and narrate expected provisioning and drift states instead of applying live changes.
- Remediation fails: execute the remediation playbook manually against the affected host or inventory group, then rerun the scan. If remediation still fails, roll back the injected drift change and re-run the baseline hardening path.
