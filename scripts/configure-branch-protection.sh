#!/usr/bin/env bash
set -euo pipefail

# Configure branch protection for a solo-developer flow:
# - PRs required
# - No human approvals required
# - Required CI checks (including Copilot review gate)
# - Conversation resolution required

usage() {
  cat <<EOF
Usage:
  GITHUB_TOKEN=<token> $0 [--owner <owner>] [--repo <repo>] [--branch <branch>] [--dry-run]

Options:
  --owner   GitHub org/user owner. Auto-detected from origin if omitted.
  --repo    Repository name. Auto-detected from origin if omitted.
  --branch  Protected branch name (default: main).
  --dry-run Print payload but do not call GitHub API.

Token requirements:
  - Fine-grained PAT with Repository administration: write
  - Or classic PAT with repo scope and admin rights on the repository
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

parse_origin() {
  local origin owner repo
  origin="$(git remote get-url origin 2>/dev/null || true)"
  [[ -n "$origin" ]] || return 1

  if [[ "$origin" =~ ^https://github.com/([^/]+)/([^/.]+)(\.git)?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
  elif [[ "$origin" =~ ^git@github.com:([^/]+)/([^/.]+)(\.git)?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
  else
    return 1
  fi

  echo "$owner" "$repo"
}

require_cmd curl
require_cmd git

OWNER=""
REPO=""
BRANCH="main"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)
      OWNER="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "$OWNER" || -z "$REPO" ]]; then
  if parsed="$(parse_origin)"; then
    # shellcheck disable=SC2086
    set -- $parsed
    OWNER="${OWNER:-$1}"
    REPO="${REPO:-$2}"
  fi
fi

[[ -n "$OWNER" ]] || die "Could not determine owner. Provide --owner."
[[ -n "$REPO" ]] || die "Could not determine repo. Provide --repo."
[[ -n "${GITHUB_TOKEN:-}" ]] || die "GITHUB_TOKEN is required."

PAYLOAD=$(cat <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Copilot review present",
      "Markdown links",
      "ShellCheck",
      "Markdownlint",
      "Repo health",
      "Terraform fmt",
      "YAML lint"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON
)

echo "Configuring branch protection for ${OWNER}/${REPO} on branch ${BRANCH}"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run enabled. Request payload:"
  echo "$PAYLOAD"
  exit 0
fi

response_file="$(mktemp)"
status_code="$({
  curl -sS -o "$response_file" -w "%{http_code}" \
    -X PUT \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${OWNER}/${REPO}/branches/${BRANCH}/protection" \
    -d "$PAYLOAD"
} || true)"

if [[ "$status_code" != "200" ]]; then
  echo "GitHub API returned HTTP ${status_code}" >&2
  cat "$response_file" >&2
  rm -f "$response_file"
  exit 1
fi

echo "Branch protection updated successfully."
rm -f "$response_file"

cat <<EOF

Manual step still required:
1. Repository settings -> Code security and analysis -> Copilot code review
2. Enable automatic Copilot reviews for pull requests

Recommended merge settings for this policy:
1. Keep squash merge enabled
2. Keep rebase merge enabled
3. Disable merge commits if you want strict linear history
EOF