# sbc-iot-runner — MQTT-only Pi field image (Alternative A, SBCC-INFRA-0001)
#
# Purpose: run `sbc iot mqtt-test` on an aarch64 Raspberry Pi without
# any AWS API credentials on the device. The operator laptop runs
# `sbc iot fetch-credentials` and `sbc iot sync-to-pi` beforehand;
# this image reads the synced PEM bundle from /data/aws-iot (bind-mounted).
#
# Build: docker compose build  (native arm64 on Pi — avoids awscrt cross-build pain)
# Run:   docker compose run --rm iot-runner iot mqtt-test
#
# Layering: lockfiles + `uv sync --no-install-project` runs first (slow awscrt).
# `sbc_config/` is copied last so Python/CLI edits only rerun the final fast sync.
#
# Build args:
#   SBC_UID  — UID for the non-root `sbc` user (default 1000).
#              Set to match the Pi host user UID for /data/aws-iot mounts
#              and 0600 private-key reads.
#
# Python 3.14 is required by pyproject.toml (requires-python = ">=3.14").
# The mcr devcontainer base ships multi-arch (linux/arm64) and includes build
# toolchain for native extension wheels (awscrt / awsiotsdk).

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

ARG SBC_UID=1000

SHELL ["/bin/bash", "-c"]

# Install uv — copy binary to /usr/local/bin so USER sbc can exec it
# (/root/.local/bin is inaccessible to non-root).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv
ENV PATH="/usr/local/bin:/root/.local/bin:$PATH"
ENV UV_LINK_MODE=copy

# Non-root runtime user.
RUN groupadd --gid "${SBC_UID}" sbc 2>/dev/null || true && \
    useradd --uid "${SBC_UID}" --gid "${SBC_UID}" \
            --shell /bin/bash --create-home \
            --non-unique sbc

WORKDIR /app

# Heavy layer: dependencies only (cached until pyproject.toml / uv.lock change).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra iot --no-dev --no-install-project

# PEM bundle mount point.
RUN mkdir -p /data/aws-iot && chown "${SBC_UID}:${SBC_UID}" /data/aws-iot

COPY infra/docker/iot-runner/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Application code last — only this layer + quick `uv sync` rerun on edits.
COPY sbc_config ./sbc_config
RUN uv sync --frozen --extra iot --no-dev \
    && chown -R "${SBC_UID}:${SBC_UID}" /app

USER sbc

ENV PATH="/usr/local/bin:${PATH}"

VOLUME ["/data/aws-iot"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["iot", "--help"]
