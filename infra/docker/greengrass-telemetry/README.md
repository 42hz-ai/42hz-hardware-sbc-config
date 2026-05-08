# greengrass-telemetry — Docker IPC publisher image

Loads **`awsiot`** in an image tagged **`sbcc/greengrass-telemetry:1.0.0`**, publishes a heartbeat JSON message to **`hello/<thing>/telemetry`** via **[Greengrass IPC](https://docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html#ipc-docker)**.

## Build tarball for Greengrass (`docker load`)

From repo root:

```bash
bash infra/docker/greengrass-telemetry/save-artifact.sh
```

Produces **`components/telemetry-publisher-docker/artifacts/com.sbc.telemetry-publisher-docker/1.0.0/telemetry-publisher-docker.tar`** (gitignored; rebuild after edits).

Pi / cross-compile:

```bash
DOCKER_DEFAULT_PLATFORM=linux/arm64 bash infra/docker/greengrass-telemetry/save-artifact.sh
```

## Deploy

See [SBCC-INFRA-0003](../../docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md); requires **`aws.greengrass.DockerApplicationManager`** on the core (deployment pulls it when the recipe lists the dependency).
