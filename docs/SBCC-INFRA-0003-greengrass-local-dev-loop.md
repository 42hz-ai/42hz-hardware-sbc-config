# SBCC-INFRA-0003 — Greengrass v2 local dev loop (devcontainer + Pi)

## What

This repo supports **AWS IoT Greengrass v2 Nucleus** on:

1. **The devcontainer** — same Linux environment as day-to-day CDK / Python work (`--network=host`, `root` user). Nucleus runs as a real core device against **IoT Core** using the same PEM bundle pattern as the Pi (`sbc iot fetch-credentials`).
2. **The Raspberry Pi** — validate the same components after `sbc iot sync-to-pi`.

A **second IoT Thing** (e.g. `hw-devcontainer-001`) is provisioned alongside `hw-pi-001` by **`IotHelloStack`** (`infra/cdk/stacks/iot_hello_stack.py`). One shared IoT policy covers **hello-world MQTT** and **Greengrass core** actions.

Local iterations use **`greengrass-cli`** (installed via a one-time **cloud deployment** of `aws.greengrass.Cli`) to run **`greengrass-cli deployment create`** against recipe + artifact directories (no S3 / cloud deployment required for the inner loop).

Two scaffold components live under `components/`:

| Component                            | Path                                                                                                                                                                  | Lifecycle                                           | Purpose                                                                                                                                                                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `com.sbc.hello-greengrass`           | [`components/hello-greengrass/`](../components/hello-greengrass/)                                                                                                     | One-shot `Run` (exits immediately)                  | Smoke test — verifies local deployment works                                                                                                                                                                                                 |
| `com.sbc.telemetry-publisher`        | [`components/telemetry-publisher/`](../components/telemetry-publisher/)                                                                                               | Long-running `Run` (loops until SIGTERM)            | Native-process IPC publisher (inner-loop spike; host **`.venv` / login-shell** caveats)                                                                                                                                                      |
| `com.sbc.telemetry-publisher-docker` | [`components/telemetry-publisher-docker/`](../components/telemetry-publisher-docker/) + [`infra/docker/greengrass-telemetry/`](../infra/docker/greengrass-telemetry/) | Long-running Docker **`Run`** with IPC socket mount | Same **`hello/<thing>/telemetry`** topic; image built by [`save-artifact.sh`](../infra/docker/greengrass-telemetry/save-artifact.sh); tarball under **`artifacts/.../telemetry-publisher-docker.tar`** (gitignored; run build before deploy) |

Artifacts live under **`artifacts/<ComponentName>/<ComponentVersion>/`** per [Greengrass CLI local deployments](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html) (e.g. **`artifacts/com.sbc.hello-greengrass/1.0.0/hello.py`** or **`…/telemetry-publisher-docker.tar`**).

## Why

- **Tight feedback loop** — edit YAML + artifacts in the repo; deploy locally in seconds without imaging or SSH to a Pi.
- **Real Greengrass semantics** — Nucleus, shadows, jobs, and component lifecycle behave like production; no local MQTT broker substitute.
- **CDK stays the contract** — Things, certs, Secrets Manager, the widened IoT policy, and (by default) **Greengrass token exchange** (IAM role + IoT role alias) live in **`IotHelloStack`**. A future `IotGreengrassStack` can add artifact buckets and fleet deployments without breaking the dev path.

## How

### Prerequisites

| Prerequisite                    | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Java 17+**                    | `openjdk-17-jre-headless` in [`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile); rebuild the devcontainer after pulling.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **AWS CLI + SSO**               | Workload profile (commonly `spikes-sitewise`), region `us-west-2` — see [Verify AWS SSO profile](#verify-aws-sso-profile) below; full runbook context in [SBCC-INFRA-0001](SBCC-INFRA-0001-iot-hello-world-cdk.md).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **CDK-deployed Things + certs** | `thingNames` in [`infra/cdk/cdk.json`](../infra/cdk/cdk.json) includes `hw-devcontainer-001`; deploy the stack, then fetch PEMs for that Thing.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Token exchange (TES)**        | **`IotHelloStack` creates this by default** — IAM role (trust `credentials.iot.amazonaws.com`), IoT role alias (default name `sbcc-iot-hello-gg-tes`, overridable via context **`greengrassTokenExchangeRoleAlias`**), and `iot:AssumeRoleWithCertificate` on the shared device policy. **`sbc iot install-greengrass`** defaults to that same alias; use stack output **`GreengrassTokenExchangeRoleAlias`** or **`--tes-role-alias`** / **`SBC_IOT_GG_TES_ROLE_ALIAS`** if yours differs. Set context **`createGreengrassTokenExchangeRole`** to `false` only if you manage TES elsewhere; then set **`greengrassTokenExchangeRoleAlias`** if the external alias must appear on the policy, or attach a separate alias-only policy per [manual installation — token exchange](https://docs.aws.amazon.com/greengrass/v2/developerguide/manual-installation.html). |
| **Docker / buildx**             | For **`telemetry-publisher-docker`**: operator machine runs **`save-artifact.sh`** (Docker CLI); **Greengrass core host** runs Docker Engine (**[`sbc iot install-pi-docker`](../sbc_config/commands/iot/install_pi_docker.py)** on the Pi). Use **`DOCKER_DEFAULT_PLATFORM=linux/arm64`** when building on amd64 for Pi. Devcontainer: **Docker socket** bind in [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json) (`mounts`). Rebuild the devcontainer after pulling. On **Linux** hosts the engine must be listening on `/var/run/docker.sock` (Docker Desktop / OrbStack expose this). **`docker-ce-cli`** + **buildx** are in [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile). See **`infra/docker/greengrass-telemetry/`** and Promotion: Docker components.                                                                        |
| **`uv sync --extra iot`**       | Run once per repo checkout (devcontainer or Pi). `awsiotsdk` is the `iot` extra in [`pyproject.toml`](../pyproject.toml); imports use **`awsiot`**. The telemetry publisher recipe sets **`SBCC_REPO_ROOT`** from **`sbccRepoRoot`** so `publisher.py` prepends **`repo/.venv/lib/pythonX.Y/site-packages`** despite Greengrass POSIX login shells rewriting **`PATH`**. Override **`sbccRepoRoot`** in [`telemetry-publisher/recipe.yaml`](../components/telemetry-publisher/recipe.yaml) when the synced path on the Pi differs.                                                                                                                                                                                                                                                                                                                                  |

`post-create.sh` **cannot** fetch secrets or run the Nucleus installer — those need live credentials and are explicit CLI steps.

### Workspace Nucleus (`SBCC_GREENGRASS_ROOT` + `sbcc-devcontainer-greengrass`)

The devcontainer sets **`SBCC_GREENGRASS_ROOT`** to **`/workspaces/<repo>/.sbcc/greengrass/v2`** and mounts the **named Docker volume** **`sbcc-devcontainer-greengrass`** at that path (**[`devcontainer.json`](../.devcontainer/devcontainer.json)** **`containerEnv`** + **`mounts`**). Nucleus, logs, **`greengrass-cli`**, and **`ipc.socket`** therefore live in a **daemon-addressable volume**, not only in the workspace bind mount.

OrbStack / Docker Desktop / **`docker.sock` forwarding**: a nested **`docker run -v …/ipc.socket:/…`** still resolves the **volume source on the daemon’s filesystem**. Paths under **`/workspaces/...`** often **don’t exist** there, so Docker may mount an **empty directory** inside the telemetry container → **`AWS_IO_SOCKET_CONNECTION_REFUSED`** when **`awsiot`** connects locally. (**Sanity:** `docker run --rm -v "$GG/ipc.socket:$GG/ipc.socket" alpine ls -la "$GG/ipc.socket"` shows an empty listing when this happens.)

**Mitigation:** `com.sbc.telemetry-publisher-docker` **1.0.1+** supports **`sbccGgIpcDockerVolume`** (**[`recipe.yaml`](../components/telemetry-publisher-docker/recipe.yaml)** **`DefaultConfiguration`**, merge via local **`--update-config`**). That branch runs **`docker run -v sbcc-devcontainer-greengrass:/sbcc-gg-ipc …`** so the daemon mounts **by volume name**.

- **`install-greengrass`** picks **`$SBCC_GREENGRASS_ROOT`** whenever **`--greengrass-root`** is omitted (**[`default_greengrass_install_root()`](../sbc_config/modules/iot/defaults.py)**).
- **Pi / bare systemd cores**: leave **`SBCC_GREENGRASS_ROOT` unset** (**`/greengrass/v2`**). Leave **`sbccGgIpcDockerVolume`** empty (**default**) so **`Run`** keeps the AWS **filepath** bind-mount.
- **Rebuild** the devcontainer after **`mounts` / `containerEnv`** drift.
- **First use** after adding the GG volume mount: reinstall Nucleus so **`ipc.socket`** is created **inside volume** **`sbcc-devcontainer-greengrass`** (`install-greengrass --reinstall --deploy-cli` as needed).

### Verify AWS SSO profile

Use this before `cdk deploy`, `sbc iot fetch-credentials`, or `sbc iot install-greengrass`.

This devcontainer **`containerEnv`** sets **`AWS_PROFILE`** (typically **`spikes-sitewise`**) and **`AWS_REGION`** (**`us-west-2`**) alongside **`SBCC_GREENGRASS_ROOT`** / **`GG`** so fresh shells inherit them after rebuilds (**override via `.devcontainer/env.local`**). It also mounts a **named Docker volume** **`sbcc-devcontainer-aws`** at **`/root/.aws`** (see [`devcontainer.json`](../.devcontainer/devcontainer.json) **`mounts`**, `type=volume`) so **`config`**, **`credentials`**, and **`sso/cache`** survive **Rebuild Container** without binding your host `~/.aws`. **First time:** run **`aws sso login`** (and add profiles to **`/root/.aws/config`**) inside the devcontainer; that data lives in the volume until you remove it (e.g. **`docker volume rm sbcc-devcontainer-aws`** with the devcontainer stopped). To reuse an existing **host** `~/.aws` instead, copy its files into the container once or switch back to a bind mount in **`devcontainer.json`**.

1. **List profiles** — confirm your workload profile name exists (often `spikes-sitewise` in this repo):

   ```bash
   aws configure list-profiles
   ```

   You can also inspect `~/.aws/config` for a `[profile …]` block with **`sso_session`** / **`sso_account_id`** / **`sso_role_name`** (SSO) rather than long‑lived access keys.

2. **Sign in** if the SSO session is missing or expired:

   ```bash
   aws sso login --profile spikes-sitewise
   ```

   Replace with your profile name if different.

3. **Point the shell at that profile** (optional but avoids passing `--profile` on every command):

   ```bash
   export AWS_PROFILE=spikes-sitewise
   export AWS_REGION=us-west-2
   ```

4. **Confirm the caller** — you should get **Account**, **UserId**, and **Arn** with no error:

   ```bash
   aws sts get-caller-identity
   ```

   The **Account** must be the workload account where **IotHelloStack** is deployed ([SBCC-INFRA-0001](SBCC-INFRA-0001-iot-hello-world-cdk.md)). The **Arn** should look like an **`assumed-role/…AWSReservedSSO_…`** principal when using SSO.

If the profile is missing, add it to `~/.aws/config` using your org’s SSO onboarding (see **`IDCTR-INFRA-0002`** in the identity-center baseline repo referenced from INFRA-0001).

### One-time setup (devcontainer)

**Rebuild** the devcontainer when **`Dockerfile`**, **`devcontainer.json`** **`containerEnv`**, **`mounts`**, or **`SBCC_GREENGRASS_ROOT`** / **`sbcc-devcontainer-greengrass`** change → **`$SBCC_GREENGRASS_ROOT`** and the GG **volume overlay** stay aligned. 2. **Deploy CDK** (if Things / policy changed):

```bash
cd infra/cdk && cdk deploy
```

3. **Fetch PEMs** for the devcontainer Thing (defaults to **`aws-iot-bundles/hw-devcontainer-001`** unless **`SBC_IOT_FETCH_OUT_DIR`** is set):

   ```bash
   sbc iot fetch-credentials --thing-name hw-devcontainer-001
   export SBC_IOT_FETCH_OUT_DIR=aws-iot-bundles/hw-devcontainer-001   # optional: pin for other commands in the same shell
   ```

4. **Install Nucleus** (partial config / existing Thing — no `--provision true`):

   ```bash
   sbc iot install-greengrass --thing-name hw-devcontainer-001 --deploy-cli
   ```

   **`install-greengrass`** defaults the TES IoT role alias to **`sbcc-iot-hello-gg-tes`** (same as **`IotHelloStack`**). Override with **`--tes-role-alias`** or **`SBC_IOT_GG_TES_ROLE_ALIAS`** if your stack uses a different name (see **`GreengrassTokenExchangeRoleAlias`** stack output). Without systemd, Nucleus runs in a **background** JVM after this command returns (installer log **`<greengrass-root>/sbcc-nucleus-install.log`** — under **`$SBCC_GREENGRASS_ROOT`** in the devcontainer, else **`/greengrass/v2/…`** unless you pass **`--greengrass-root`**); use **`--foreground`** to keep the terminal attached. Re-runs **skip** the installer when **`packages/`** or **`work/`** already exists under **`--greengrass-root`** (or **`$SBCC_GREENGRASS_ROOT`**) and only **refresh PEMs** from the bundle; use **`--reinstall`** to force a full install.

   **`--bundle-dir`** defaults the same way as fetch (**`aws-iot-bundles/<thing-name>`** or **`SBC_IOT_FETCH_OUT_DIR`**).

   `--deploy-cli` creates a one-time **cloud deployment** for `aws.greengrass.Cli`. Nucleus must be **running** to apply it; only then does **`<greengrass-root>/bin/greengrass-cli`** appear ([install CLI](https://docs.aws.amazon.com/greengrass/v2/developerguide/install-gg-cli.md)). Poll **`aws greengrassv2 get-deployment --deployment-id …`** (id printed by the command) until the deployment completes on the Thing. If **`bin/`** is empty, check **`pgrep -af Greengrass.jar`**, deployment status, and **`<greengrass-root>/logs/`**. Skip the flag if you prefer the console.

   Use **`--no-setup-system-service`** (default) inside devcontainers; use **`--setup-system-service`** on a real systemd Pi.

5. **Verify CLI** (after the Cli deployment has completed on-device):

   ```bash
   GG="${SBCC_GREENGRASS_ROOT:-/greengrass/v2}"
   "$GG/bin/greengrass-cli" help
   ```

### Daily dev loop

Throughout this section, **`GG`** resolves to **`$SBCC_GREENGRASS_ROOT`** in the SBCC devcontainer (workspace **`.sbcc/greengrass/v2`**), or **`/greengrass/v2`** on cores where the env var is unset (typical Pi).

```bash
export GG="${SBCC_GREENGRASS_ROOT:-/greengrass/v2}"
```

1. Edit **recipes** and **artifacts** under `components/<name>/`. For **`deployment create`**, artifact files must live under **`--artifactDir/<ComponentName>/<ComponentVersion>/`** (see AWS [**gg-cli-deployment**](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html)).
2. Deploy locally from repo root (the **`--merge`** flag adds this component version to the deployment; without it, Nucleus may only reconcile existing cloud components such as **`aws.greengrass.Cli`**, and your custom component will not run):

   **One-shot smoke test (`hello-greengrass`):**

   ```bash
   "$GG/bin/greengrass-cli" deployment create \
     --recipeDir components/hello-greengrass \
     --artifactDir components/hello-greengrass/artifacts \
     --merge "com.sbc.hello-greengrass=1.0.0"
   ```

   **Continuous publisher (`telemetry-publisher-docker`, recommended for Pi parity):**

   1. Build the image tarball (needs a working **Docker Engine + CLI** on your machine; devcontainer must have the socket mounted):

      ```bash
      bash infra/docker/greengrass-telemetry/save-artifact.sh
      ```

      For Raspberry Pi OS on **arm64**:

      ```bash
      DOCKER_DEFAULT_PLATFORM=linux/arm64 bash infra/docker/greengrass-telemetry/save-artifact.sh
      ```

   2. Deploy locally (**devcontainer OrbStack forwarding** merges **`sbccGgIpcDockerVolume`** so nested **`docker run`** mounts nucleus IPC by **Docker volume name**; **omit `--update-config` on Pi** — default empty uses AWS filepath bind-mount):

      ```bash
      "$GG/bin/greengrass-cli" deployment create \
        --recipeDir components/telemetry-publisher-docker \
        --artifactDir components/telemetry-publisher-docker/artifacts \
        --merge "com.sbc.telemetry-publisher-docker=1.0.1" \
        --update-config '{"com.sbc.telemetry-publisher-docker":{"MERGE":{"sbccGgIpcDockerVolume":"sbcc-devcontainer-greengrass"}}}'
      ```

      **Pi** (omit **`--update-config`** — keep **`sbccGgIpcDockerVolume`** defaulted empty):

      ```bash
      "$GG/bin/greengrass-cli" deployment create \
        --recipeDir components/telemetry-publisher-docker \
        --artifactDir components/telemetry-publisher-docker/artifacts \
        --merge "com.sbc.telemetry-publisher-docker=1.0.1"
      ```

      The **`Run`** step follows [Use IPC in Docker container components](https://docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html): a merged **`sbccGgIpcDockerVolume`** triggers **`docker run -v`** with that **Docker volume name** mapped to **`/sbcc-gg-ipc`**, **`AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT=/sbcc-gg-ipc/ipc.socket`**, **`SVCUID`**, **`AWS_IOT_THING_NAME`** — see recipe. Leaving **`sbccGgIpcDockerVolume`** empty (**Pi**) uses the AWS-documented **filepath** bind mount **`$AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT`** passthrough plus matching **`-e`**.

   3. Logs: **`tail -f $GG/logs/com.sbc.telemetry-publisher-docker.log`**

   **Continuous publisher (native `telemetry-publisher`, devcontainer-only caveats):**

   ```bash
   "$GG/bin/greengrass-cli" deployment create \
     --recipeDir components/telemetry-publisher \
     --artifactDir components/telemetry-publisher/artifacts \
     --merge "com.sbc.telemetry-publisher=1.0.2"
   ```

3. **Component stdout** is not shown on the CLI terminal. Tail the component log to watch output:

   ```bash
   # hello-greengrass: one-shot, look for "hello-greengrass: ok"
   tail -f $GG/logs/com.sbc.hello-greengrass.log

   # telemetry-publisher (native)
   tail -f $GG/logs/com.sbc.telemetry-publisher.log

   # telemetry-publisher-docker
   tail -f $GG/logs/com.sbc.telemetry-publisher-docker.log
   ```

   To watch all custom-component activity at once: `grep com.sbc $GG/logs/greengrass.log`.

4. **Subscribe to the telemetry topic** in a second terminal to see messages arrive in IoT Core:

   ```bash
   # Requires aws CLI + jq; adjust --profile / --region as needed
   THING=hw-devcontainer-001
   ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text)
   sbc iot mqtt-test --endpoint "$ENDPOINT" \
     --thing-name "$THING" \
     --topic "hello/$THING/telemetry"
   ```

   Or use the **AWS IoT Core MQTT test client** in the console (Test > MQTT test client → subscribe to `hello/+/telemetry`).

5. Inspect component status via **`greengrass-cli`** ([reference](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-reference.md)):

   ```bash
   /greengrass/v2/bin/greengrass-cli component list
   ```

   A healthy long-running component shows lifecycle state **RUNNING** (not **FINISHED**).

6. To stop the publisher without removing it, use a new deployment that sets the component to **DISABLED** or simply restart Nucleus; to remove it, deploy without the `--merge` flag for that component name.

### Troubleshooting (& notes from devcontainer demo)

- **No `greengrass-cli` binary** — Nucleus install alone does not install it. Use **`install-greengrass --deploy-cli`** (or console) so **`aws.greengrass.Cli`** is applied while **`Greengrass.jar`** is running; then **`<greengrass-root>/bin/greengrass-cli`** appears (often **`$SBCC_GREENGRASS_ROOT/bin`** in SBCC devcontainer). [`install-greengrass`](../sbc_config/commands/iot/install_greengrass.py) prints a **`get-deployment`** line for the Cli job id.
- **Cloud deployment polling** — **`aws greengrassv2 list-deployments`** often shows nothing useful **without** **`--target-arn`** (your Thing ARN). Prefer **`aws greengrassv2 get-deployment --deployment-id …`** using the id from **`install-greengrass`**.
- **Local `deployment create`** — After submit, use **`greengrass-cli deployment status -i <LocalDeploymentId>`**; **`SUCCEEDED`** usually arrives within seconds (no fixed **`sleep`**). Those ids are the **on-core local ledger**, not the same as **`CreateDeployment`** ids unless you are correlating deliberately.
- **`greengrass.log`:** **`Skipping file …/hello.py because it was not recognized as a recipe`** is **normal** (Greengrass scans **`--artifactDir`** for recipe files; **`hello.py`** is an artifact).
- **Hello component behavior** — Recipe **`Run`** is **one-shot** (script exits). Expect lifecycle **FINISHED**, not a long-lived **RUNNING** state. Stdout is **`hello-greengrass: ok`** in **`logs/com.sbc.hello-greengrass.log`** (and often mirrored in **`greengrass.log`**).
- **Telemetry-publisher-docker (`com.sbc.telemetry-publisher-docker`)** — Requires **Docker Engine on the core**, **`install` + `Run` with `RequiresPrivilege: true`**, and **`aws.greengrass.DockerApplicationManager`** (**[`telemetry-publisher-docker/recipe.yaml`](../components/telemetry-publisher-docker/recipe.yaml)**). **OrbStack / forwarded `docker.sock`:** nested **`docker run -v`** on a **`/workspaces/.../ipc.socket` filepath often mounts an **empty dir** → **`AWS_IO_SOCKET_CONNECTION_REFUSED`**. SBCC **`devcontainer.json`** mounts nucleus data on **`sbcc-devcontainer-greengrass`**; **`1.0.1+`** uses **`--update-config`** to merge **`sbccGgIpcDockerVolume: sbcc-devcontainer-greengrass`** so **`Run`** does **`docker run -v`** by **volume name** (see Workspace Nucleus). **Rebuild** → **`install-greengrass --reinstall --deploy-cli`** seeds **`ipc.socket`** into that volume. **Pi**: omit **`--update-config`** (default empty **`sbccGgIpcDockerVolume`** → filepath bind). Rebuild **`telemetry-publisher-docker.tar`** when **`infra/docker/greengrass-telemetry/`** changes — keep **`save-artifact.sh`\*\* **`ART_VERSION`**, **`ComponentVersion`**, and **`docker load` / `docker run`** tags aligned (**`docker run … sbcc/greengrass-telemetry:1.0.0`** today).
- **Telemetry-publisher (`com.sbc.telemetry-publisher`)** — Lifecycle **RUNNING**; tails show `published [N]` lines. Pip package **`awsiotsdk`** installs import name **`awsiot`**. Dependencies live under **`.venv/`** (**`uv sync --extra iot`**). Greengrass invokes lifecycle scripts under POSIX **`sh -lc`**, login profiles rewrite **`PATH`**, so the recipe exports **`SBCC_REPO_ROOT`** from **`sbccRepoRoot`** (`DefaultConfiguration` in [`components/telemetry-publisher/recipe.yaml`](../components/telemetry-publisher/recipe.yaml)); point **`sbccRepoRoot`** at the synced repo on the Pi. After changing `publisher.py` or `recipe.yaml`, **bump `ComponentVersion`** (or prune **`<greengrass-root>/packages/artifacts/.../<old>/`**) — same versions reuse cached artifact trees.
- **IPC authorization errors** — If the publisher logs `AccessDenied` or similar from Nucleus, confirm the `accessControl` block is correctly indented inside `DefaultConfiguration` in the recipe and that the topic in `resources` (`hello/+/telemetry`) matches the topic the script publishes to (`hello/<thingName>/telemetry`). IPC auth is evaluated by Nucleus before the MQTT publish reaches IoT Core.
- **IoT Core policy** — The existing `IotHelloStack` policy already covers `hello/${iot:Connection.Thing.ThingName}/*` for Publish/Receive/Subscribe, so no CDK changes are needed to run the publisher.
- **Idempotent Nucleus install** — Re-runs skip the installer when **`packages/`** or **`work/`** exists under **`--greengrass-root`** unless **`--reinstall`**; PEMs still refresh from the bundle.

### Promotion: Pi validation

1. `sbc iot fetch-credentials --thing-name hw-pi-001` (writes **`aws-iot-bundles/hw-pi-001`** by default).
2. Sync repo + bundle: **`sbc iot sync-to-pi`** (default **`--thing-name hw-pi-001`** matches that path) or **`sbc iot sync-to-pi --thing-name … --bundle-dir …`** when needed.
3. On the Pi: **`sbc iot install-greengrass`** (typically **`--setup-system-service`**), **`--bundle-dir`** pointing at the synced bundle path on the Pi; deploy CLI once; run the same **`greengrass-cli deployment create`** flows (or use a cloud deployment from CDK later).

### Promotion: Docker container components

There are **two** common patterns in the AWS docs — easy to conflate:

1. **[Run AWS IoT Greengrass Core software in a Docker container](https://docs.aws.amazon.com/greengrass/v2/developerguide/run-greengrass-docker.html)** (tutorial-style “Greengrass in Docker”) — the **Nucleus** (and often local dev tooling) runs **inside** one image. Useful for lab/provisioning stories; on a real Pi it means **privileged mounts**, socket/proxy choices, and extra care if you also want **nested** app containers (see [Prescriptive Guidance — GG in Docker + app containers](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/deploy-containerized-applications-on-aws-iot-greengrass-version-2-running-as-a-docker-container.html) and Docker-in-Docker tradeoffs).

2. **Nucleus on the host + containerized _custom_ components** — what most teams use when the goal is **“Dependencies live in the workload image.”** You install **Docker Engine on the core** (already in this repo’s Pi path via [`sbc iot install-pi-docker`](../sbc_config/commands/iot/install_pi_docker.py)), deploy **[`aws.greengrass.DockerApplicationManager`](https://docs.aws.amazon.com/greengrass/v2/developerguide/docker-application-manager-component.html)**, and author a recipe that references a **`docker:`** image artifact and a **`Run`** step such as **`docker run` / Compose** per **[Run a Docker container](https://docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html)**. For **PublishToIoTCore** from inside the app container, AWS documents **mounting the Greengrass IPC socket** using **`AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT`** (same page). Private ECR pulls typically add **`aws.greengrass.TokenExchangeService`** as a dependency.

**Why this is a good “path forward” vs the native Python spike:** the **Pi and devcontainer converge on the same image digest** (build with **`docker buildx`** for **`linux/arm64`** and **`linux/amd64`**), no host **`python3` / `sh -lc` / `.venv` coupling**, and corporate networks can pin **ECR** instead of device-side **`pip`**. The tradeoff is operational: **Docker on the core**, image **pull** sizing, and **Compose / `docker run` flags** for IPC (and any bind mounts you need).

**Scaffold in this repo:** [`infra/docker/greengrass-telemetry/`](../infra/docker/greengrass-telemetry/) (image + [`save-artifact.sh`](../infra/docker/greengrass-telemetry/save-artifact.sh)) and [`components/telemetry-publisher-docker/`](../components/telemetry-publisher-docker/) (recipe — **`docker load` + IPC `docker run`**). A later **`IotGreengrassStack`** can push the same Dockerfile to **ECR** and switch the recipe artifact from tarball to **`docker:…`** URIs for fleet rollouts.

**Native `com.sbc.telemetry-publisher`:** optional devcontainer-only spike; **`com.sbc.telemetry-publisher-docker`** is the path that matches Pi and production without **`SBCC_REPO_ROOT` / login-shell PATH** coupling.

### IoT policy reference (this stack)

The shared policy in `IotHelloStack` includes:

- **Hello world** — `Connect` / `Publish` / `Subscribe` / `Receive` on `hello/${iot:Connection.Thing.ThingName}/*` with `iot:Connection.Thing.IsAttached`.
- **Greengrass** — `iot:Connect` on `client/${iot:Connection.Thing.ThingName}*`; shadow, job, and health MQTT ARNs use `$aws/things/${iot:Connection.Thing.ThingName}/…` so one shared policy stays under AWS’s **2048-character** limit (literal per-Thing ARNs did not). **Service API** actions: `GetComponentVersionArtifact`, `ResolveComponentCandidates`, `GetDeploymentConfiguration`, `ListThingGroupsForCoreDevice`. **Client-device** actions (`PutCertificateAuthorities`, `VerifyClientDevice*`, `Discover`) are omitted to leave headroom for `AssumeRoleWithCertificate` and a long role alias — attach an extra IoT policy when you use [local client devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html).
- **TES (default)** — `iot:AssumeRoleWithCertificate` on `arn:aws:iot:<region>:<account>:rolealias/<alias>` for the CDK-created alias (or the name from **`greengrassTokenExchangeRoleAlias`** when you override or use an external alias with **`createGreengrassTokenExchangeRole: false`**).

Official baseline: [Device authentication — minimal core device policy](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html#greengrass-core-minimal-iot-policy).

### After a devcontainer rebuild

Greengrass **`$SBCC_GREENGRASS_ROOT`** overlays the repo at **`.sbcc/greengrass/v2`** and is backed by the **named Docker volume** **`sbcc-devcontainer-greengrass`** (persisted independently of **`Rebuild Container`**). AWS SSO / PEM bundles under **`aws-iot-bundles/…`** (bind mount / **`SBC_IOT_FETCH_OUT_DIR`**) typically survive unchanged.

Run **`install-greengrass --deploy-cli`** again when **`ipc.socket` / nucleus tree is missing** or **`greengrass-cli` vanished** (**`docker volume rm`** / clean slate wipes **`sbcc-devcontainer-greengrass`** too). Prefer **`fetch-credentials`** only when certs rotate or **`aws-iot-bundles/…`** was deleted.

Migrating **off** **`/greengrass/v2`** (legacy): **`echo "$SBCC_GREENGRASS_ROOT"`** — stop stray **`Greengrass.jar`**, then **`install-greengrass --reinstall --deploy-cli`** with **`--greengrass-root` omitted** so **`ipc.socket`** materializes inside **`sbcc-devcontainer-greengrass`**.

## Cross-links

- [SBCC-INFRA-0001 — IoT hello CDK + CLI](SBCC-INFRA-0001-iot-hello-world-cdk.md)
- [SBCC-INFRA-0002 — Network / IT briefing](SBCC-INFRA-0002-iot-core-network-it-briefing.md)
- Skill: [`.cursor/skills/greengrass-local-dev/SKILL.md`](../.cursor/skills/greengrass-local-dev/SKILL.md)
- What is Greengrass: [AWS — What is AWS IoT Greengrass?](https://docs.aws.amazon.com/greengrass/v2/developerguide/what-is-iot-greengrass.html)

## Nucleus version

**2.17.0** is pinned in installer defaults and examples ([`sbc_config/modules/iot/greengrass_install.py`](../sbc_config/modules/iot/greengrass_install.py)). Bump with the **Greengrass release notes**, then update this doc and the **`greengrass-local-dev`** skill in the **same change**.
