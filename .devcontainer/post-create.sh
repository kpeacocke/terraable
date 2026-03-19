#!/bin/bash
set -euo pipefail

echo "Installing Terraform and related tools..."

if ! command -v sudo >/dev/null 2>&1; then
  echo "Error: sudo is required to install system packages in post-create." >&2
  exit 1
fi

# Update package list
sudo apt-get update

# Install wget if not already installed
sudo apt-get install -y wget

# Refresh Yarn apt key/source to avoid signature failures from stale image state.
if [ -f /etc/apt/sources.list.d/yarn.list ]; then
  wget -O- https://dl.yarnpkg.com/debian/pubkey.gpg | gpg --dearmor | sudo tee /usr/share/keyrings/yarn-archive-keyring.gpg > /dev/null
  echo "deb [signed-by=/usr/share/keyrings/yarn-archive-keyring.gpg] https://dl.yarnpkg.com/debian stable main" | sudo tee /etc/apt/sources.list.d/yarn.list > /dev/null
fi

# Install Terraform from HashiCorp's official repository
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list > /dev/null
sudo apt-get update
sudo apt-get install -y terraform

# Verify installation
terraform --version

echo "Terraform installation completed successfully!"
