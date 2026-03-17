---
description: Use when editing markdown docs, runbooks, architecture notes, and contributor guidance for terraable.
applyTo: "**/*.md"
---

# Documentation standards

- Use Australian English.
- Keep docs practical and execution-focused.
- Prefer short sections with concrete actions.

## Required structure for operational docs
- Purpose and scope.
- Prerequisites.
- Inputs and configuration.
- Procedure.
- Expected outputs.
- Troubleshooting and recovery.

## Security expectations
- Do not include real secrets, tokens, private endpoints, or sensitive infrastructure details.
- Use redacted examples and placeholder values.
- Reinforce responsible disclosure expectations aligned with `SECURITY.md`.

## Quality expectations
- Keep terminology consistent across Terraform, AAP/AWX, EDA, and control-plane UI docs.
- When documenting workflows, include both success path and failure path behaviour.
- For milestone-related docs, state which phase is being advanced (MVP, Phase 2, Phase 3, Demo Readiness, Public Forkability).
