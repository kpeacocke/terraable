# Terraable Agents

This document lists available specialised agents and when to invoke them. Type `/` in chat to select an agent, or reference the name directly.

## Agent reference

| Agent | Purpose | When to use | Key outputs |
|-------|---------|-------------|-------------|
| **mvp-architect** | Architecture design and contracts | Designing new features, targets, or handoff paths; clarifying interfaces before coding. | Problem/scope, constraints, proposed architecture, interface contracts, risks, acceptance criteria, sequenced plan. |
| **platform-builder** | Feature implementation | Delivering code for milestone features; building end-to-end slices (trigger, logic, status, error handling). | Feature code, tests, docs updates, completion checklist sign-off. |
| **security-compliance** | Hardening, scanning, drift, remediation | Designing/reviewing controls, compliance logic, evidence collection; strengthening detection and remediation. | Control objectives, detection methods, remediation actions, evidence outputs, security review checklist. |
| **demo-readiness** | Runbooks, offline mode, forkability | Writing demonstration flows, offline/mock mode, fork-and-run guides, storytelling sequences. | Audience/scenario, preconditions, step-by-step flows, expected outputs, failure recovery paths. |

## Example triggers

**Design a new target path (AWS):**
> "Use the mvp-architect agent. Design the Terraform-to-Ansible handoff contract for AWS target support (Phase 2 issue #19)."

**Implement SSH hardening control:**
> "Use the security-compliance agent. Design and implement SSH root login hardening validation for baseline controls (MVP issue #10)."

**Build monorepo structure:**
> "Use the platform-builder agent. Implement monorepo structure with clear Terraform and Ansible paths (MVP issue #1)."

**Write MVP demo runbook:**
> "Use the demo-readiness agent. Write the MVP demo runbook covering provision → baseline → scan → remediate → evidence (Demo Readiness issue #17)."

## Agent selection heuristic

- **Architecture or interface unclear?** → `mvp-architect`
- **Feature is ready to code?** → `platform-builder`
- **Control, compliance, or security path?** → `security-compliance`
- **Demo, runbook, or fork experience?** → `demo-readiness`
- **Still unsure?** Ask Copilot directly and it will recommend the best agent.

## Global Copilot instructions

All agents operate under the constraints defined in [copilot-instructions.md](./copilot-instructions.md):
- MVP first, phase-aligned outcomes.
- Terraform provisioning ↔ Ansible operations strict separation.
- Australian English documentation.
- No secrets/credentials in code or examples.
- Security-first, demo-reliable, fork-friendly.
- 100% test coverage, mutation and integration tests required.
- Snyk code scanning for first-party generated code.

See [copilot-instructions.md](./copilot-instructions.md) for full context.
