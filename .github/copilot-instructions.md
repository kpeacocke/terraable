# Copilot Instructions for terraable

## Project intent
- Build a reference demo that provisions with HCP Terraform and operationalises with Ansible Automation Platform.
- Show the full lifecycle: provision, baseline harden, scan, detect drift, remediate, and prove with evidence.
- Keep the repository easy to fork, run, and demo by contributors.

## Product outcomes to optimise for
- MVP outcomes:
- Monorepo structure and clear Terraform-to-Ansible handoff contract.
- Initial OpenShift substrate path.
- Selectable portal deployment path for `rhdh` and `backstage`.
- Baseline control implementation for CIS-aligned hardening and SSH root login controls.
- Control-plane UI with action and evidence/status panels.
- Compliance scan and manual remediation workflows.
- Architecture documentation sufficient for first-time contributors.
- Phase 2 outcomes:
- Additional targets (AWS, Azure, OKD, local workshop abstraction).
- Optional AWX lab-mode substitute.
- Security profile variants and richer compliance trend views.
- Event-driven remediation via EDA webhook/rulebook path.
- Phase 3 outcomes:
- Additional targets (GCP, VMware, Parallels, Hyper-V).
- Local environment auto-detection helper.
- Richer platform storytelling features and expanded controls.
- End-to-end observability dashboard.
- Demo and forkability outcomes:
- Demo runbook and offline/mock mode.
- Fork-and-run guidance and safe sample environment defaults.

## Non-negotiable engineering principles
- Preserve clear separation of concerns between provisioning (Terraform) and operational controls (Ansible).
- Make workflows deterministic and replayable for demos.
- Prefer explicit contracts and typed data exchange over implicit assumptions.
- Build for least privilege and secure defaults.
- Keep implementation testable and observable.

## Security and compliance rules
- Treat security as a first-class feature.
- Do not introduce credentials, secrets, or tokens into code, docs, examples, tests, logs, or generated artefacts.
- Prefer environment variables and redacted examples.
- Add or update security checks when introducing new control logic.
- Preserve responsible disclosure expectations from `SECURITY.md`.
- For generated first-party code in a Snyk-supported language, run a Snyk code scan and remediate high-confidence findings before completion.

## Delivery and change quality
- Keep changes small and cohesive.
- Include acceptance criteria in issue or PR text when implementing scoped work.
- Add or update tests for changed behaviour.
- Include basic docs updates when adding new modules, targets, workflows, or UI behaviour.
- Prefer backwards-compatible schema or contract evolution.
- Explicitly document any breaking change and migration path.

## Documentation style and language
- Use Australian English in all documentation and user-facing text.
- Be concise, concrete, and operational.
- Where relevant, include:
- Preconditions.
- Inputs and outputs.
- Failure modes and remediation steps.

## When planning or implementing
- Tie proposed changes to milestone outcomes (MVP, Phase 2, Phase 3, Demo Readiness, Public Forkability).
- Highlight risks across:
- Security and compliance impact.
- Drift detection and remediation reliability.
- Demo reliability in low-connectivity/offline contexts.
- If scope is unclear, default to the smallest increment that advances the current milestone without constraining later phases.

## Pull request guidance
- PR summaries should include:
- Problem statement.
- Approach and trade-offs.
- Test evidence.
- Security implications.
- Documentation updates.
- For UI or workflow changes, include before/after notes and execution path details.

## What to avoid
- Avoid coupling provider-specific logic into shared abstractions.
- Avoid hidden side effects in automation workflows.
- Avoid introducing optional complexity before MVP path is clear.
- Avoid broad refactors unrelated to the issue being solved.
