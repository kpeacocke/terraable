#!/usr/bin/env bash
# check-tools.sh - verify that all contributor tooling is present and meets
# minimum version requirements.
#
# Usage: bash scripts/check-tools.sh
# Exit code 0 = all tools present; 1 = one or more tools missing.

set -euo pipefail

PASS=0
FAIL=1
overall=0

extract_version() {
  local raw="$1"
  local version
  version=$(printf "%s" "$raw" | grep -Eo '[0-9]+(\.[0-9]+){1,3}' | head -1 || true)
  printf "%s" "$version"
}

version_ge() {
  local current="$1"
  local minimum="$2"
  if [[ -z "$current" ]]; then
    return 1
  fi

  local IFS=.
  local -a current_parts minimum_parts
  local max_parts=0
  local idx=0
  local current_part=0
  local minimum_part=0

  read -r -a current_parts <<< "$current"
  read -r -a minimum_parts <<< "$minimum"

  max_parts=${#current_parts[@]}
  if (( ${#minimum_parts[@]} > max_parts )); then
    max_parts=${#minimum_parts[@]}
  fi

  for (( idx=0; idx<max_parts; idx++ )); do
    current_part=${current_parts[idx]:-0}
    minimum_part=${minimum_parts[idx]:-0}

    if (( 10#$current_part > 10#$minimum_part )); then
      return 0
    fi
    if (( 10#$current_part < 10#$minimum_part )); then
      return 1
    fi
  done

  return 0
}

check() {
  local name="$1"
  local cmd="$2"
  local min_version="$3"
  local hint="$4"
  local raw_output
  local parsed_version

  if command -v "$name" > /dev/null 2>&1; then
    raw_output=$(eval "$cmd" 2>&1 || true)
    parsed_version=$(extract_version "$raw_output")
    if version_ge "$parsed_version" "$min_version"; then
      printf "  %-20s OK   %s (>= %s)\n" "$name" "${parsed_version:-unknown}" "$min_version"
    else
      printf "  %-20s OLD  %s (requires >= %s)\n" "$name" "${parsed_version:-unknown}" "$min_version"
      overall=$FAIL
    fi
  else
    printf "  %-20s MISSING — %s\n" "$name" "$hint"
    overall=$FAIL
  fi
}

echo "Checking contributor tooling..."
echo ""

check "python3"          "python3 --version"          "3.11.0" "Install Python 3.11+ from https://python.org"
check "poetry"           "poetry --version"           "1.8.0" "curl -sSL https://install.python-poetry.org | python3 -"
check "terraform"        "terraform version"          "1.9.0" "https://developer.hashicorp.com/terraform/install"
check "ansible"          "pip show ansible | grep Version | awk '{print \$2}'" "10.0.0" "pip install ansible"
check "ansible-rulebook" "ansible-rulebook --version" "1.0.0" "pip install ansible-rulebook"
check "shellcheck"       "shellcheck --version"       "0.9.0" "apt install shellcheck  or  brew install shellcheck"
check "markdownlint-cli2" "markdownlint-cli2 --version" "0.14.0" "npm install -g markdownlint-cli2"
check "yamllint"         "yamllint --version"         "1.35.0" "pip install yamllint"
check "git"              "git --version"              "2.40.0" "Install Git from https://git-scm.com"

echo ""

if [[ $overall -eq $PASS ]]; then
  echo "All tools present."
else
  echo "One or more tools are missing. Install them and re-run this script."
  exit 1
fi
