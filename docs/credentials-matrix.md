# Credential Matrix

## Intent
Define the external credentials required to run Terraable without mocks, with clear ownership, scope, minimum permission policy, and storage guidance per environment.

## Preconditions
- You are running live mode (not offline/mock).
- Secrets are stored in an approved secret manager (not committed to this repository).
- Service accounts are used in preference to personal credentials.

## Environment Model

| Environment | Purpose | Suggested Owner | Access Pattern |
|---|---|---|---|
| Dev | Day-to-day engineering validation | Platform engineering | Shared service accounts, short-lived credentials |
| Test | CI and integration verification | Platform engineering + security | Dedicated non-human identities, automated rotation |
| Demo | Customer/demo execution path | Demo operations | Dedicated demo identities, tightly scoped |
| Prod | Production-like control plane operation | Platform operations + security | Least privilege, approval gates, full audit trail |

## Credential Inventory

| Domain | Credential | Used By | Minimum Scope / Permission Policy | Env Required |
|---|---|---|---|---|
| HCP Terraform | HCP API token (`TF_TOKEN_<hostname>`) | `terraable/hcp_terraform.py`, control plane backend | Read runs/applies/state-versions/outputs for required workspaces only; no org-wide admin | Dev, Test, Demo, Prod |
| HCP Terraform | Workspace execution identity (VCS or API run) | Terraform workflow execution | Execute runs only in approved workspaces; deny unrelated projects | Dev, Test, Demo, Prod |
| AWS | IAM role or key pair | `terraform/modules/substrate_aws` | Least privilege for VPC, compute, IAM pass-role, storage, DNS only if used; region constrained where possible | Test, Demo, Prod (Dev if AWS path is used) |
| Azure | Service principal (`ARM_CLIENT_ID/SECRET/TENANT/SUBSCRIPTION`) | `terraform/modules/substrate_azure` | Least privilege for RG/network/compute and required dependent services only; scope to subscription/resource group | Test, Demo, Prod (Dev if Azure path is used) |
| OpenShift/OKD | API token or kubeconfig | OpenShift/OKD substrate and portal deployment workflows | Namespace/project-scoped where possible; cluster-admin only where explicitly required | Test, Demo, Prod |
| Registry | Container registry pull secret/token | RHDH/Backstage deployment paths | Read-only pull for runtime, write only where image publishing is required | Dev, Test, Demo, Prod |
| Git SCM | Repository deploy key/token | AWX/AAP project sync, catalog/bootstrap content | Read-only for project checkout in automation contexts | Dev, Test, Demo, Prod |
| AAP/AWX | Controller auth (`AWX_HOST`, username/password or token) | AWX bootstrap and job launch workflows | Job template/project/inventory operations only; avoid full admin for day-to-day runs | Dev, Test, Demo, Prod |
| EDA | Webhook shared secret / source auth token | EDA event ingestion and rulebook triggers | Validate source authenticity; only accepted event source identities | Test, Demo, Prod |
| Host Access | SSH private key + automation user | Ansible hardening/scan/remediation roles | Host groups limited to Terraable-managed targets; sudo/become rights only for required tasks | Dev, Test, Demo, Prod |
| DNS | DNS API token | Ingress/domain setup where applicable | Zone-scoped record management only (no account-wide admin) | Test, Demo, Prod |
| Certificates | ACME or internal CA credentials | TLS setup for portals/controllers | Issue/renew only for approved domains; no broad CA admin | Test, Demo, Prod |
| Secrets Backend | Vault/secret manager auth | Runtime secret retrieval for all workflows | Read specific secret paths only; no wildcard read of unrelated paths | Dev, Test, Demo, Prod |
| Notifications (optional) | Webhook/API token (Slack/Teams/PagerDuty) | Operational alerting paths | Send-only to approved channels | Demo, Prod |

## Owner And Rotation Matrix

| Credential Domain | Primary Owner | Secondary Owner | Rotation Target |
|---|---|---|---|
| HCP Terraform | Platform engineering | Security | 90 days or less |
| AWS/Azure cloud identities | Platform engineering | Security | 90 days or less (or short-lived role credentials) |
| OpenShift/OKD tokens | Platform operations | Security | 30-90 days depending on token model |
| AAP/AWX auth | Automation operations | Security | 90 days or less |
| SSH keys | Platform operations | Security | 90 days or less |
| DNS and certificate credentials | Platform operations | Security | 90 days or less |
| Secrets backend identities | Security | Platform engineering | 30-90 days depending on policy |

## Required Environment Variables (Reference)
These variables are referenced by the repository today:
- `TF_TOKEN_<hostname>` and optional `TERRAABLE_TFC_HOSTNAME`
- `AWX_HOST`, `AWX_USERNAME`, `AWX_PASSWORD`
- `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_SUBSCRIPTION_ID`, `ARM_TENANT_ID`
- `TERRAABLE_DEFAULT_TARGET`, `TERRAABLE_DEFAULT_PORTAL`, `TERRAABLE_DEFAULT_SECURITY_PROFILE`

See `.env.example` for examples and safe defaults.

## Failure Modes And Remediation

| Failure Mode | Typical Symptom | Remediation |
|---|---|---|
| Missing HCP token | HCP API calls fail with auth errors | Set `TF_TOKEN_<hostname>` for the configured hostname |
| Over-scoped cloud identity blocked by policy | Terraform apply denied by organisation policy | Replace with least-privilege role and allowed resource scopes |
| Under-scoped cloud identity | Terraform plan/apply permission denied | Add only missing service actions required by the module |
| AWX auth invalid | Controller bootstrap/job launch fails | Rotate AWX token/password and re-test controller connectivity |
| SSH key mismatch | Ansible unreachable or permission denied | Update inventory credential binding and rotate key pair |
| EDA secret mismatch | Webhook events rejected | Reconcile webhook source secret and sender configuration |

## Storage And Handling Rules
- Never commit secrets to git, docs, tests, logs, or generated artefacts.
- Store credentials in approved secret stores and inject at runtime.
- Use dedicated service accounts per environment; do not reuse personal identities.
- Prefer short-lived credentials where platform support exists.
- Audit access and rotation in line with organisational policy.
