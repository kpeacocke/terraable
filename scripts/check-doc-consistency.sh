#!/usr/bin/env bash
set -euo pipefail

# Lightweight guardrails to catch high-impact doc drift.
# This intentionally checks a small set of phrases and anchors.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

fail() {
  echo "doc-consistency: $1" >&2
  exit 1
}

# 1) Ban known-stale phrases that previously caused contradictory guidance.
if git grep -nI -E 'only control-plane backend wired end-to-end remains|Module groundwork only|additional target selectors remain contract and module scaffolding|informational/UI-only' -- README.md docs modes; then
  fail "found stale wording in docs"
fi

# 2) Token guidance: docs should present Terraform CLI token naming as primary.
for file in README.md docs/lab-guide.md modes/lab/README.md docs/credentials-matrix.md docs/hcp-terraform.md; do
  grep -Eq 'TF_TOKEN_<hostname>|TF_TOKEN_\*' "$file" || fail "missing TF_TOKEN guidance in $file"
done

# 3) Alias guidance: where HCP_TERRAFORM_TOKEN appears in user-facing docs,
#    it should be described as an alias/backwards-compatible path.
for file in README.md docs/lab-guide.md modes/lab/README.md; do
  if grep -q 'HCP_TERRAFORM_TOKEN' "$file"; then
    grep -Eq 'alias|backwards-compatible' "$file" || fail "HCP_TERRAFORM_TOKEN is not described as alias in $file"
  fi
done

# 4) Source-of-truth section must exist in README.
grep -q '^## Source Of Truth$' README.md || fail "README is missing Source Of Truth section"

echo "doc-consistency: OK"
