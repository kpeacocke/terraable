# MVP Demo Runbook

## Preconditions
- Python 3.11+, Terraform 1.5+, and Ansible 10 are available.
- Repository checks pass locally.
- Target credentials are configured through environment variables.

## Inputs
- Target selector: `openshift`, `aws`, or `local-lab`
- Portal selector: `rhdh` or `backstage`
- Security profile: `baseline` or `strict`
- EDA toggle: enabled or disabled

## Presenter Flow
1. Start with control-plane selectors and create environment request.
2. Show Terraform stage evidence and run identifier.
3. Trigger baseline application.
4. Trigger compliance scan and show pass state.
5. Inject SSH drift (`PermitRootLogin yes`) and re-run scan.
6. Trigger remediation and verify recovered scan status.
7. Highlight evidence panel timeline for all actions.

## Expected Outcomes
- Baseline and remediation actions return success status.
- Compliance scan fails during injected drift and passes post-remediation.
- Evidence panel reflects every action with status and detail.

## Failure Modes and Recovery
- Terraform run unavailable: switch to offline/mock mode for narrative continuity.
- Scan output missing: rerun scan action and verify inventory connectivity.
- Remediation fails: execute remediation playbook manually and rerun scan.
