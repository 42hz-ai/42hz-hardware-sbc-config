# SBCC-INFRA-0003 — Greengrass v2 local dev loop (devcontainer + Pi)

## What

This repo supports **AWS IoT Greengrass v2 Nucleus** on:

1. **The devcontainer** — same Linux environment as day-to-day CDK / Python work (`--network=host`, `root` user). Nucleus runs as a real core device against **IoT Core** using the same PEM bundle pattern as the Pi (`sbc iot fetch-credentials`).
2. **The Raspberry Pi** — validate the same components after `sbc iot sync-to-pi`.

A **second IoT Thing** (e.g. `hw-devcontainer-001`) is provisioned alongside `hw-pi-001` by **`IotHelloStack`** (`infra/cdk/stacks/iot_hello_stack.py`). One shared IoT policy covers **hello-world MQTT** and **Greengrass core** actions.

Local iterations use **`greengrass-cli`** (installed via a one-time **cloud deployment** of `aws.greengrass.Cli`) to run **`greengrass-cli deployment create`** against recipe + artifact directories (no S3 / cloud deployment required for the inner loop).

Scaffold component: [`components/hello-greengrass/`](../components/hello-greengrass/) — recipe at repo root of that folder; artifacts under **`artifacts/<ComponentName>/<ComponentVersion>/`** per [Greengrass CLI local deployments](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html) (e.g. **`artifacts/com.sbc.hello-greengrass/1.0.0/hello.py`**).

## Why

- **Tight feedback loop** — edit YAML + artifacts in the repo; deploy locally in seconds without imaging or SSH to a Pi.
- **Real Greengrass semantics** — Nucleus, shadows, jobs, and component lifecycle behave like production; no local MQTT broker substitute.
- **CDK stays the contract** — Things, certs, Secrets Manager, the widened IoT policy, and (by default) **Greengrass token exchange** (IAM role + IoT role alias) live in **`IotHelloStack`**. A future `IotGreengrassStack` can add artifact buckets and fleet deployments without breaking the dev path.

## How

### Prerequisites

| Prerequisite                          | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Java 17+**                          | `openjdk-17-jre-headless` in [`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile); rebuild the devcontainer after pulling.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **AWS CLI + SSO**                     | Workload profile (commonly `spikes-sitewise`), region `us-west-2` — see [Verify AWS SSO profile](#verify-aws-sso-profile) below; full runbook context in [SBCC-INFRA-0001](SBCC-INFRA-0001-iot-hello-world-cdk.md).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **CDK-deployed Things + certs**       | `thingNames` in [`infra/cdk/cdk.json`](../infra/cdk/cdk.json) includes `hw-devcontainer-001`; deploy the stack, then fetch PEMs for that Thing.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Token exchange (TES)**              | **`IotHelloStack` creates this by default** — IAM role (trust `credentials.iot.amazonaws.com`), IoT role alias (default name `sbcc-iot-hello-gg-tes`, overridable via context **`greengrassTokenExchangeRoleAlias`**), and `iot:AssumeRoleWithCertificate` on the shared device policy. **`sbc iot install-greengrass`** defaults to that same alias; use stack output **`GreengrassTokenExchangeRoleAlias`** or **`--tes-role-alias`** / **`SBC_IOT_GG_TES_ROLE_ALIAS`** if yours differs. Set context **`createGreengrassTokenExchangeRole`** to `false` only if you manage TES elsewhere; then set **`greengrassTokenExchangeRoleAlias`** if the external alias must appear on the policy, or attach a separate alias-only policy per [manual installation — token exchange](https://docs.aws.amazon.com/greengrass/v2/developerguide/manual-installation.html). |
| **Docker / buildx** (optional, later) | For **Docker container components** on the Pi, build multi-arch images in the devcontainer; see “Promotion: Docker components”.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

`post-create.sh` **cannot** fetch secrets or run the Nucleus installer — those need live credentials and are explicit CLI steps.

### Verify AWS SSO profile

Use this before `cdk deploy`, `sbc iot fetch-credentials`, or `sbc iot install-greengrass`.

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

1. **Rebuild** the devcontainer (if Dockerfile changed) → Java is on `PATH`.
2. **Deploy CDK** (if Things / policy changed):

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

   **`install-greengrass`** defaults the TES IoT role alias to **`sbcc-iot-hello-gg-tes`** (same as **`IotHelloStack`**). Override with **`--tes-role-alias`** or **`SBC_IOT_GG_TES_ROLE_ALIAS`** if your stack uses a different name (see **`GreengrassTokenExchangeRoleAlias`** stack output). Without systemd, Nucleus runs in a **background** JVM after this command returns (installer log **`/greengrass/v2/sbcc-nucleus-install.log`** unless you change **`--greengrass-root`**); use **`--foreground`** to keep the terminal attached. Re-runs **skip** the installer when **`packages/`** or **`work/`** already exists under **`--greengrass-root`** and only **refresh PEMs** from the bundle; use **`--reinstall`** to force a full install.

   **`--bundle-dir`** defaults the same way as fetch (**`aws-iot-bundles/<thing-name>`** or **`SBC_IOT_FETCH_OUT_DIR`**).

   `--deploy-cli` creates a one-time **cloud deployment** for `aws.greengrass.Cli`. Nucleus must be **running** to apply it; only then does **`/greengrass/v2/bin/greengrass-cli`** appear ([install CLI](https://docs.aws.amazon.com/greengrass/v2/developerguide/install-gg-cli.md)). Poll **`aws greengrassv2 get-deployment --deployment-id …`** (id printed by the command) until the deployment completes on the Thing. If **`bin/`** is empty, check **`pgrep -af Greengrass.jar`**, deployment status, and **`/greengrass/v2/logs/`**. Skip the flag if you prefer the console.

   Use **`--no-setup-system-service`** (default) inside devcontainers; use **`--setup-system-service`** on a real systemd Pi.

5. **Verify CLI** (after the Cli deployment has completed on-device):

   ```bash
   /greengrass/v2/bin/greengrass-cli help
   ```

### Daily dev loop

1. Edit **recipes** and **artifacts** under `components/<name>/`. For **`deployment create`**, artifact files must live under **`--artifactDir/<ComponentName>/<ComponentVersion>/`** (see AWS [**gg-cli-deployment**](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html)).
2. Deploy locally from repo root (the **`--merge`** flag adds this component version to the deployment; without it, Nucleus may only reconcile existing cloud components such as **`aws.greengrass.Cli`**, and your custom component will not run):

   ```bash
   /greengrass/v2/bin/greengrass-cli deployment create \
     --recipeDir components/hello-greengrass \
     --artifactDir components/hello-greengrass/artifacts \
     --merge "com.sbc.hello-greengrass=1.0.0"
   ```

3. **Component stdout** is not shown on the CLI terminal. After a successful deploy, tail **`/greengrass/v2/logs/com.sbc.hello-greengrass.log`** (or **`grep com.sbc /greengrass/v2/logs/greengrass.log`**). The hello artifact prints **`hello-greengrass: ok`** once **`Run`** finishes.
4. Inspect logs / component status via **`greengrass-cli`** ([reference](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-reference.md)).

### Troubleshooting (& notes from devcontainer demo)

- **No `greengrass-cli` binary** — Nucleus install alone does not install it. Use **`install-greengrass --deploy-cli`** (or console) so **`aws.greengrass.Cli`** is applied while **`Greengrass.jar`** is running; then **`/greengrass/v2/bin/greengrass-cli`** appears. [`install-greengrass`](../sbc_config/commands/iot/install_greengrass.py) prints a **`get-deployment`** line for the Cli job id.
- **Cloud deployment polling** — **`aws greengrassv2 list-deployments`** often shows nothing useful **without** **`--target-arn`** (your Thing ARN). Prefer **`aws greengrassv2 get-deployment --deployment-id …`** using the id from **`install-greengrass`**.
- **Local `deployment create`** — After submit, use **`greengrass-cli deployment status -i <LocalDeploymentId>`**; **`SUCCEEDED`** usually arrives within seconds (no fixed **`sleep`**). Those ids are the **on-core local ledger**, not the same as **`CreateDeployment`** ids unless you are correlating deliberately.
- **`greengrass.log`:** **`Skipping file …/hello.py because it was not recognized as a recipe`** is **normal** (Greengrass scans **`--artifactDir`** for recipe files; **`hello.py`** is an artifact).
- **Hello component behavior** — Recipe **`Run`** is **one-shot** (script exits). Expect lifecycle **FINISHED**, not a long-lived **RUNNING** state. Stdout is **`hello-greengrass: ok`** in **`logs/com.sbc.hello-greengrass.log`** (and often mirrored in **`greengrass.log`**).
- **Idempotent Nucleus install** — Re-runs skip the installer when **`packages/`** or **`work/`** exists under **`--greengrass-root`** unless **`--reinstall`**; PEMs still refresh from the bundle.

### Promotion: Pi validation

1. `sbc iot fetch-credentials --thing-name hw-pi-001` (writes **`aws-iot-bundles/hw-pi-001`** by default).
2. Sync repo + bundle: **`sbc iot sync-to-pi`** (default **`--thing-name hw-pi-001`** matches that path) or **`sbc iot sync-to-pi --thing-name … --bundle-dir …`** when needed.
3. On the Pi: **`sbc iot install-greengrass`** (typically **`--setup-system-service`**), **`--bundle-dir`** pointing at the synced bundle path on the Pi; deploy CLI once; run the same **`greengrass-cli deployment create`** flows (or use a cloud deployment from CDK later).

### Promotion: Docker container components

Greengrass supports **`aws.greengrass.DockerApplicationManager`**. The devcontainer already has **Docker CLI + buildx**; build **linux/arm64** images for the Pi (`docker buildx build --platform linux/arm64`) and reference the image URI in a component recipe when you move past native-process components. A future **`IotGreengrassStack`** can own ECR + fleet deployments.

### IoT policy reference (this stack)

The shared policy in `IotHelloStack` includes:

- **Hello world** — `Connect` / `Publish` / `Subscribe` / `Receive` on `hello/${iot:Connection.Thing.ThingName}/*` with `iot:Connection.Thing.IsAttached`.
- **Greengrass** — `iot:Connect` on `client/${iot:Connection.Thing.ThingName}*`; shadow, job, and health MQTT ARNs use `$aws/things/${iot:Connection.Thing.ThingName}/…` so one shared policy stays under AWS’s **2048-character** limit (literal per-Thing ARNs did not). **Service API** actions: `GetComponentVersionArtifact`, `ResolveComponentCandidates`, `GetDeploymentConfiguration`, `ListThingGroupsForCoreDevice`. **Client-device** actions (`PutCertificateAuthorities`, `VerifyClientDevice*`, `Discover`) are omitted to leave headroom for `AssumeRoleWithCertificate` and a long role alias — attach an extra IoT policy when you use [local client devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html).
- **TES (default)** — `iot:AssumeRoleWithCertificate` on `arn:aws:iot:<region>:<account>:rolealias/<alias>` for the CDK-created alias (or the name from **`greengrassTokenExchangeRoleAlias`** when you override or use an external alias with **`createGreengrassTokenExchangeRole: false`**).

Official baseline: [Device authentication — minimal core device policy](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html#greengrass-core-minimal-iot-policy).

### After a devcontainer rebuild

`/greengrass/v2` is **inside** the container — re-run **`install-greengrass`** (and optionally `--deploy-cli`). PEMs on the host / bind-mounted **`aws-iot-bundles/…`** (or a single **`aws-iot-bundle`**) often survive; **fetch-credentials** is only needed if the bundle is missing or rotated.

## Cross-links

- [SBCC-INFRA-0001 — IoT hello CDK + CLI](SBCC-INFRA-0001-iot-hello-world-cdk.md)
- [SBCC-INFRA-0002 — Network / IT briefing](SBCC-INFRA-0002-iot-core-network-it-briefing.md)
- Skill: [`.cursor/skills/greengrass-local-dev/SKILL.md`](../.cursor/skills/greengrass-local-dev/SKILL.md)
- What is Greengrass: [AWS — What is AWS IoT Greengrass?](https://docs.aws.amazon.com/greengrass/v2/developerguide/what-is-iot-greengrass.html)

## Nucleus version

**2.17.0** is pinned in installer defaults and examples ([`sbc_config/modules/iot/greengrass_install.py`](../sbc_config/modules/iot/greengrass_install.py)). Bump with the **Greengrass release notes**, then update this doc and the **`greengrass-local-dev`** skill in the **same change**.
