#!/usr/bin/env bash
# Build the telemetry image and write a tarball for Greengrass ``docker load``
# (matches AWS pattern in https://docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html ).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TAG="sbcc/greengrass-telemetry:1.0.0"
ART_VERSION="1.0.1"
OUT="${ROOT}/components/telemetry-publisher-docker/artifacts/com.sbc.telemetry-publisher-docker/${ART_VERSION}/telemetry-publisher-docker.tar"

PLATFORM_ARGS=()
if [[ -n "${DOCKER_DEFAULT_PLATFORM:-}" ]]; then
  PLATFORM_ARGS=(--platform "${DOCKER_DEFAULT_PLATFORM}")
fi

docker build \
  "${PLATFORM_ARGS[@]}" \
  -t "${TAG}" \
  -f "${ROOT}/infra/docker/greengrass-telemetry/Dockerfile" \
  "${ROOT}/infra/docker/greengrass-telemetry"

mkdir -p "$(dirname "${OUT}")"
docker save "${TAG}" -o "${OUT}"

echo "Wrote ${OUT} (deploy with telemetry-publisher-docker recipe)"
