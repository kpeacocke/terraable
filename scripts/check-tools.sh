#!/usr/bin/env bash
# check-tools.sh — verify that all contributor tooling is present and meets
# minimum version requirements.
#
# Usage: bash scripts/check-tools.sh
# Exit code 0 = all tools present; 1 = one or more tools missing.

set -euo pipefail

PASS=0
FAIL=1
overall=0

check() {
  local name="$1"
  local cmd="$2"
  local hint="$3"

  if command -v "$name" > /dev/null 2>&1; then
    version=$(eval "$cmd" 2>&1 | head -1)
    printf "  %-20s OK   %s\n" "$name" "$version"
  else
    printf "  %-20s MISSING — %s\n" "$name" "$hint"
    overall=$FAIL
  fi
}

echo "Checking contributor tooling..."
echo ""

check "python3"        "python3 --version"         "Install Python 3.11+ from https://python.org"
check "poetry"         "poetry --version"           "curl -sSL https://install.python-poetry.org | python3 -"
check "terraform"      "terraform version"          "https://developer.hashicorp.com/terraform/install"
check "ansible"        "ansible --version"          "pip install ansible"
check "ansible-rulebook" "ansible-rulebook --version" "pip install ansible-rulebook"
check "shellcheck"     "shellcheck --version"       "apt install shellcheck  or  brew install shellcheck"
check "markdownlint-cli2" "markdownlint-cli2 --version" "npm install -g markdownlint-cli2"
check "yamllint"       "yamllint --version"         "pip install yamllint"
check "git"            "git --version"              "Install Git from https://git-scm.com"

echo ""

if [[ $overall -eq $PASS ]]; then
  echo "All tools present."
else
  echo "One or more tools are missing. Install them and re-run this script."
  exit 1
fi
