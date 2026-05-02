#!/usr/bin/env bash
#
# Install AWS CLI v2 inside the devcontainer without rebuilding the image.
# Matches the logic in .devcontainer/Dockerfile (official bundle, amd64/arm64).
#
# Run from repo root:
#   bash .devcontainer/install-aws-cli.sh
#
# Or copy/paste the marked block into an interactive shell (same as running this file).

set -euo pipefail

# --- copy/paste block starts (same as executing this script) ---

# Refresh apt metadata (needed so install can find curl/unzip packages).
apt-get update &&
  # Install tools: curl = download ZIP, unzip = extract bundle,
  # ca-certificates = HTTPS trust, less = pager some installers expect.
  apt-get install -y ca-certificates curl unzip less &&
  # Drop downloaded package lists to save space (Dockerfile habit; optional).
  rm -rf /var/lib/apt/lists/*

# Pick the right official Linux build (x86_64 vs ARM64).
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
amd64) AWS_CLI_ZIP="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" ;;
arm64) AWS_CLI_ZIP="https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" ;;
*)
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
  ;;
esac

# Download AWS's all-in-one installer bundle (large — often the slow step).
# Omit -s on curl if you want a progress bar: curl -fSL ...
curl -fsSL "$AWS_CLI_ZIP" -o /tmp/awscliv2.zip

# Extract to /tmp/aws (quiet).
unzip -q /tmp/awscliv2.zip -d /tmp

# Run AWS's installer: copies aws to /usr/local (default). --update replaces existing.
/tmp/aws/install --update

# Remove download + extract tree (~100MB+) from /tmp.
rm -rf /tmp/awscliv2.zip /tmp/aws

# Forget cached command paths so the new aws binary resolves in this shell.
hash -r

# Show v2 version string.
aws --version

# --- copy/paste block ends ---
