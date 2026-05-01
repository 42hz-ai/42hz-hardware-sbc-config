FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

SHELL ["/bin/bash", "-c"]

# Update package lists first
RUN apt-get update

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Project deps: use `uv` in the workspace (see post-create.sh). System pip only
# for .devcontainer/configure_git.py (runs before `uv sync`; no project venv).
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir "click>=8.2.1" "rich>=13.7.0"

# Install node and npm
RUN apt install -y ca-certificates gnupg && \
  mkdir -p /etc/apt/keyrings && \
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
  NODE_MAJOR=22 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
  apt update && \
  apt install -y nodejs && \
  rm -rf /var/lib/apt/lists/*

# Do not run `npm install -g npm@latest` here: upgrading npm over NodeSource's
# bundled npm often fails (e.g. MODULE_NOT_FOUND promise-retry). The distro
# npm is enough for global prettier below.

# Install prettier
RUN npm install -g prettier

# Install AWS CDK CLI globally so `cdk synth` / `cdk deploy` work in the
# devcontainer. See docs/SBCC-INFRA-0001-iot-hello-world-cdk.md.
RUN npm install -g aws-cdk

# Install vim (fixed: update package lists first)
RUN apt-get update && \
  apt-get install -y vim && \
  rm -rf /var/lib/apt/lists/*


RUN apt-get update && \
  apt-get install -y ca-certificates curl gnupg && \
  install -m 0755 -d /etc/apt/keyrings && \
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
  chmod a+r /etc/apt/keyrings/docker.gpg && \
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
  apt-get update && \
  apt-get install -y docker-ce-cli docker-buildx-plugin docker-compose-plugin && \
  rm -rf /var/lib/apt/lists/*


ENV UV_LINK_MODE=copy

# libguestfs: use qemu in user mode when /dev/kvm is unavailable (typical in containers).
ENV LIBGUESTFS_BACKEND=direct

# jsii (the aws-cdk-lib runtime bridge) prints a 14-line banner on Node 20.
# Cursor-server bundles Node 20 and prepends it to PATH, so any shell launched
# inside Cursor sees the banner. Real deploys (CI / outside Cursor) get the
# devcontainer's Node 22 and would not need this. Revisit when Cursor-server
# ships Node 22 (or jsii drops Node 20 entirely after 2026-10-30).
ENV JSII_SILENCE_WARNING_DEPRECATED_NODE_VERSION=1

# CLI networking diagnostics (ping, dig, wget, curl, ss, nc, etc.)
RUN apt-get update && \
  apt-get install -y iputils-ping dnsutils curl wget iproute2 netcat-openbsd && \
  rm -rf /var/lib/apt/lists/*

# Raspberry Pi imaging (sbc imaging): guestfs (virt-copy-in, virt-customize, guestfish); openssl for userconf.
RUN apt-get update && \
  apt-get install -y libguestfs-tools openssl xz-utils && \
  rm -rf /var/lib/apt/lists/*
