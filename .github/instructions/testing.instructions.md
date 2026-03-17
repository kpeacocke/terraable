---
description: Use when creating or reviewing tests to ensure 100% coverage, mutation testing, and integration validation for terraable.
applyTo: "**/*_test.{tf,py,sh,yml}; **/tests/**; **/test_*.{py,sh}; **/conftest.py"
---

# Testing standards

- Require 100% code coverage for all modified behaviour.
- Include mutation testing to verify test efficacy.
- Mandate integration tests for workflows that span Terraform, Ansible, or control-plane components.
- Keep tests deterministic, repeatable, and suitable for offline/mock contexts.

## Coverage rules

- All functions, methods, and conditional branches must have test cases.
- All error paths and edge cases require explicit tests.
- Configuration schema validation must be tested.
- Use coverage reports (`pytest --cov`, Terraform test coverage, etc.) to identify gaps.
- Coverage reports should be included in PR evidence.

## Mutation testing

- Use language-appropriate mutation tools:
  - Python: `mutmut` or `cosmic-ray`.
  - Terraform: Custom test harnesses that validate control sensitivity.
  - Bash/shell: `bash-mutation-testing` or equivalent.
- Mutation score should be ≥ 80% (tests kill 80% of introduced mutations).
- Document which mutations are expected to survive and why.
- Include mutation test results in PR.

## Integration testing

- For multi-component workflows (e.g., Terraform → Ansible → control validation):
- Create isolated integration test scenarios.
- Validate input/output contracts at each handoff.
- Test both success and failure paths (e.g., remediation rollback).
- Include one happy-path and one drift/error scenario per workflow.
- For demo-critical paths, add offline/mock mode equivalents.

## Test structure

- Unit tests: Fast, isolated, high coverage.
- Integration tests: Slower, real payloads, validate contracts.
- Contract tests: Validate Terraform-to-Ansible handoff schemas.
- Smoke tests: Quick sanity checks for demo/workshop readiness.

## Documentation and evidence

- Document test rationale for complex or non-obvious cases.
- Include test execution logs in PR.
- For Terraform/Ansible, include example playbook/apply output showing control validation.
- For UI/workflow tests, include screenshots or execution traces when relevant.

## Quality bar

- No feature ships without 100% coverage + mutation tests passing.
- Every control logic change requires integration tests validating detection and remediation paths.
- Demo-critical workflows must have offline/mock equivalents and test coverage.
