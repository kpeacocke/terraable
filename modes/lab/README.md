# Lab Mode

Lab mode targets constrained environments — workshops, learning labs, and fork-and-run contributors — where a full AAP subscription is not available. AWX is used as a drop-in controller substitute.

## When to use

- Workshop delivery without licensed AAP
- CI pipelines validating Ansible content against AWX
- Fork-and-run contributors testing the full workflow path without cloud infra

## Target status

| Target | Notes |
|--------|-------|
| `local-lab` | Live-executable. Recommended first target. Runs against localhost or a local VM. Requires an HCP Terraform token via `HCP_TERRAFORM_TOKEN` or `TF_TOKEN_<hostname>`. |
| `gcp` | Live-executable. Requires `GOOGLE_APPLICATION_CREDENTIALS` and `HCP_TERRAFORM_TOKEN`. |
| `vmware` | Live-executable. Requires `HCP_TERRAFORM_TOKEN`. Uses Terraform contract scaffold. |
| `parallels` | Live-executable. Requires `HCP_TERRAFORM_TOKEN`. Defaults to localhost management host. |
| `hyper-v` | Live-executable. Requires `HCP_TERRAFORM_TOKEN`. Defaults to localhost Hyper-V host. |
| `aws` | Live-executable via dedicated backend (`AWSBackend`). Requires AWS IAM credentials and `HCP_TERRAFORM_TOKEN`. |
| `azure` | Live-executable via dedicated backend (`AzureBackend`). Requires ARM service principal and `HCP_TERRAFORM_TOKEN`. |
| `okd` | Live-executable via dedicated backend (`OKDBackend`). Requires OpenShift API token and `HCP_TERRAFORM_TOKEN`. |
| `openshift` | Contract and module scaffolding only. Appears in the contract docs, but current control-plane API target routing does not provide an OpenShift backend path yet (planned Phase 2). |

## AWX setup

1. Stand up AWX — see [AWX operator install guide](https://github.com/ansible/awx-operator).
2. Set environment variables in `.env`:

   ```
   AWX_HOST=https://awx.example.local
   AWX_USERNAME=admin
   AWX_PASSWORD=<redacted>
   TERRAABLE_SCM_URL=https://github.com/<your-username>/terraable.git
   ```

3. Bootstrap the Terraable project and job templates:

   ```bash
   ansible-playbook ansible/awx/bootstrap_awx.yml
   ```

4. Verify all four job templates were created:
   - `terraable-operationalise`
   - `terraable-compliance-scan`
   - `terraable-remediate-ssh`
   - `terraable-drift-second-scenario`

## EDA in lab mode

EDA is optional in lab mode. To enable:

1. Install `ansible-rulebook`:

   ```bash
   pip install ansible-rulebook
   ansible-galaxy collection install ansible.eda
   ```

2. Run the SSH compliance drift rulebook:

   ```bash
   ansible-rulebook \
     --rulebook ansible/eda/rulebooks/ssh_compliance_drift.yml \
     --inventory ansible/inventory.yml \
     --vars ansible/eda/vars/eda_vars.yml
   ```

3. Enable EDA mode in the UI and trigger a drift event to test end-to-end.
