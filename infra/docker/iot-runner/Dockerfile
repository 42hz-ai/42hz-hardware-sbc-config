# sbc-iot-runner — MQTT-only Pi field image (Alternative A, SBCC-INFRA-0001)
#
# Purpose: run `sbc iot mqtt-test` on an aarch64 Raspberry Pi without
# any AWS API credentials on the device.  The operator laptop runs
# `sbc iot fetch-credentials` and `sbc iot sync-to-pi` beforehand;
# this image reads the synced PEM bundle from /data/aws-iot (bind-mounted).
#
# Build: docker compose build  (native arm64 on Pi — avoids awscrt cross-build pain)
# Run:   docker compose run --rm iot-runner iot mqtt-test
#
# Build args:
#   SBC_UID  — UID for the non-root `sbc` user (default 1000).
#              Set to match the Pi host user UID so /data/aws-iot mounts
#              work without permission errors on 0600 private keys.
#
# Python 3.14 is required by pyproject.toml (requires-python = ">=3.14").
# The mcr devcontainer base ships multi-arch (linux/arm64) and includes build
# toolchain for native extension wheels (awscrt / awsiotsdk).
# Swap for python:3.14-slim-bookworm + gcc/libffi-dev if image size matters
# and the slim base proves sufficient after awscrt builds cleanly on it.

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

ARG SBC_UID=1000

SHELL ["/bin/bash", "-c"]

# Install uv (same installer as .devcontainer/Dockerfile).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
ENV UV_LINK_MODE=copy

# Non-root runtime user.
# Use --non-unique so build is idempotent if UID 1000 is already taken.
RUN groupadd --gid "${SBC_UID}" sbc 2>/dev/null || true && \
    useradd --uid "${SBC_UID}" --gid "${SBC_UID}" \
            --shell /bin/bash --create-home \
            --non-unique sbc

# Copy only what uv needs for the dependency install layer.
WORKDIR /app
COPY pyproject.toml uv.lock ./

# Copy source — needed for the editable install.
COPY sbc_config ./sbc_config
COPY README.md ./

# Install the iot extra (awsiotsdk + awscrt); frozen = reproducible from lock.
# Build as root so native wheels compile; runtime as non-root.
RUN uv sync --frozen --extra iot --no-dev

# PEM bundle mount point.  Owned by sbc so 0600 private-key reads work.
RUN mkdir -p /data/aws-iot && chown sbc:sbc /data/aws-iot

# Entrypoint shim: auto-injects --endpoint from /data/aws-iot/endpoint.txt
# when running `iot mqtt-test` without an explicit --endpoint flag.
COPY infra/docker/iot-runner/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER sbc

# Make uv available to the sbc user (installed as root above).
ENV PATH="/root/.local/bin:${PATH}"

VOLUME ["/data/aws-iot"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["iot", "--help"]
