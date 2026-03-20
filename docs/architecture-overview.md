# Terraable Architecture Overview

## Scope
This overview defines the MVP architecture for Terraform provisioning and Ansible operationalisation.

## Core Principle
Terraform provisions infrastructure. Ansible operationalises and enforces controls. The integration contract remains explicit and typed.

## High-Level Flow
1. Control-plane UI collects selectors and environment request.
2. Terraform stage runs against selected substrate and emits outputs.
3. Integration layer builds the canonical handoff payload.
4. AAP workflow consumes runtime variables and executes operational playbooks.
5. Evidence and status are surfaced back to the UI.

## Modes
- Showcase mode: Full workflow with live endpoints.
- Lab mode: Reduced setup using local or substitute controllers.
- Offline/mock mode: Simulated evidence for rehearsals.

## Selectors
- `target_platform`: `openshift`, `aws`, `local-lab`
- `portal_impl`: `rhdh`, `backstage`
- `security_profile`: `baseline`, `strict`
- `eda`: UI-only selector for future event-driven path (`enabled` / `disabled`, Phase 2, not present in MVP handoff contract)

## Component Boundaries
- Terraform content: substrate provisioning and outputs.
- Ansible content: baseline, portal deployment, scan, drift, remediation.
- Integration service: payload validation and orchestration sequencing.
- UI: user actions and evidence/status rendering.

## Terraform to Ansible Handoff
See `docs/handoff-contract.md` for canonical schema and validation behaviour.

## MVP Risks
- Security and compliance: drift controls must remain deterministic.
- Reliability: UI actions should produce machine-readable evidence.
- Demo constraints: workflows should support low-connectivity rehearsal modes.
