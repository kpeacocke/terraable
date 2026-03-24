# MVP Demo Runbook

## Purpose and Scope
This runbook defines the step-by-step execution path for the MVP demo narrative.
It covers selector setup, baseline and compliance actions, controlled drift injection, remediation, and evidence review.
It applies to showcase, lab, and offline/mock execution paths used by contributors and presenters.

## Prerequisites
- Python 3.11+, Terraform 1.9+, and Ansible 10 are available.
- Repository checks pass locally.
- Target credentials are configured through environment variables.

## Credential Readiness Checklist
Use this checklist before any live demo run. For full credential definitions, owners, and minimum scope guidance, see [Credential Matrix](credentials-matrix.md).

### Sign-off Rules
- A run environment is `Ready` only when all required credential domains below are provisioned, validated, and not expired.
- Use dedicated service accounts, not personal accounts.
- Record sign-off evidence in your team run log or ticket system.

### Environment Sign-off
| Environment | Status | Signed By | Date | Notes |
|---|---|---|---|---|
| Dev | Pending sign-off |  |  |  |
| Test | Pending sign-off |  |  |  |
| Demo | Pending sign-off |  |  |  |
| Prod | Pending sign-off |  |  |  |

### Required Credential Domains
Mark each row as `Ready` or `N/A` for the selected target path.

| Credential Domain | Dev | Test | Demo | Prod | Validation Check |
|---|---|---|---|---|---|
| HCP Terraform API token and workspace access | Pending | Pending | Pending | Pending | `HcpTerraformClient.get_run_status()` returns successfully for a known run |
| Target platform identity (AWS/Azure/OpenShift/OKD/local) | Pending | Pending | Pending | Pending | Target API auth succeeds and Terraform plan can read provider data |
| AAP/AWX controller credentials | Pending | Pending | Pending | Pending | Controller API auth succeeds and a test job template can be launched |
| SSH/host credentials for operational targets | Pending | Pending | Pending | Pending | Ansible ad-hoc ping or equivalent host reachability check passes |
| Registry/SCM credentials for portal path | Pending | Pending | Pending | Pending | Portal artefacts/templates can be fetched without interactive auth |
| EDA webhook and source authentication (if enabled) | Pending | Pending | Pending | Pending | Test event accepted and routed to the expected rulebook path |
| DNS/TLS credentials (if applicable) | Pending | Pending | Pending | Pending | DNS write and certificate issuance/renewal smoke checks pass |
| Secrets backend access (if used) | Pending | Pending | Pending | Pending | Required secret paths are readable by runtime identities only |

### Go/No-Go Gate
- Go: all required rows are `Ready` for the chosen environment and target selectors.
- No-Go: any required row remains `Pending` or failed validation.

## Procedure Inputs
- Target selector surface: `local-lab`, `aws`, `azure`, `okd`, `gcp`, `vmware`, `parallels`, or `hyper-v` (`openshift` remains scaffold-only in this branch)
- Executable MVP target path: `local-lab`
- Portal selector: `rhdh` or `backstage`
- Security profile: `baseline` or `strict`
- EDA toggle: `enabled` or `disabled` (MVP script does not depend on EDA; enabling EDA affects event and evidence messaging in live paths)

For the scripted MVP flow, use `local-lab + backstage`. Additional executable targets can be used for extended demos when credentials and platform prerequisites are met.

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

- Control-plane backend connectivity (showcase mode):
  - The UI is static, but the API backend enforces credential readiness for live actions by target and portal.
  - If you see auth-related blockers, verify target-specific environment variables and UI authentication inputs, then re-run **Create environment** to refresh readiness state.
  - If live connectivity remains unstable, switch to offline/mock mode and continue the narrative with deterministic evidence.

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
