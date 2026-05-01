# SBCC-INFRA-0001 — IoT hello world (CDK + Lambda + Secrets Manager)

> **Living doc.** Maintainership: see `.cursor/skills/infra-cdk/SKILL.md`. Update this file in the same change as any modification listed in _Living-doc stewardship clause_ there.

## At a glance

| Topic          | Value                                                                                                                                                                                                                                                                             |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stack          | `IotHelloStack` ([`infra/cdk/stacks/iot_hello_stack.py`](../infra/cdk/stacks/iot_hello_stack.py))                                                                                                                                                                                 |
| Account        | **`iotea-workloads-spikes-sitewise`** — **`867492128540`** (`us-west-2`; Workloads ▸ Spikes OU). Same id as the [`iotea-spike-preston-sitewise`](/workspaces/iotea-spike-preston-sitewise/README.md) SSO table — **confirm in the AWS access portal** if your assignments differ. |
| Region         | **`us-west-2`**                                                                                                                                                                                                                                                                   |
| CLI profile    | **`spikes-sitewise`** (mirrors `iotea-spike-preston-sitewise`)                                                                                                                                                                                                                    |
| CDK            | Python — `aws-cdk-lib >= 2.200`, `constructs ~= 10` (root `pyproject.toml [project.optional-dependencies] cdk`)                                                                                                                                                                   |
| Lambda runtime | `lambda.Runtime.PYTHON_3_13`                                                                                                                                                                                                                                                      |
| Operator CLI   | **`sbc iot {describe-endpoint, fetch-credentials, mqtt-test, sync-to-pi, install-pi-docker, decommission-thing, list-orphan-certs}`**                                                                                                                                             |
| Shared spine   | [`sbc_config/modules/iot/lifecycle.py`](../sbc_config/modules/iot/lifecycle.py) — imported by both the CLI and the custom-resource Lambda                                                                                                                                         |

**IT / network stakeholders:** egress, firewalls, PrivateLink, and hostname vs IP policy are summarized in **[SBCC-INFRA-0002 — IoT Core network & egress (IT briefing)](SBCC-INFRA-0002-iot-core-network-it-briefing.md)**.

## Why

A Raspberry Pi (Phase A: 1 device, Phase B: 17 devices) needs **per-device MQTT identity** so AWS IoT Core can authenticate it, scope it to its own topic namespace, and later let **Greengrass v2** download deployments. Three constraints drove this design:

1. **Don't bake private keys into the SD image.** A leaked image leaks the cert. Each device must mint its own certificate (or have one minted _for_ it and pulled at provisioning time).
2. **Don't commit PEMs to git.** Private keys + certs live in Secrets Manager, not stack outputs and not the repo.
3. **No orphan resources.** Stack delete must detach + inactivate + delete the cert + delete the secret in the right order or AWS leaves a free-floating cert nobody owns.

This is the **hello-world** version of provisioning — one Thing, one cert, one MQTT publish — sized for a spike but with the lifecycle and per-Thing scoping a production stack would also need.

### Why not …

- **Hard-coded certs in the SD image.** Fails (1) — leaked image leaks the device fleet.
- **Click-ops console certs + cert.csv in git.** Fails (2). Also no rotation story.
- **Fleet Provisioning / claim certs.** Better for thousands of devices; overkill for ≤17 and adds the bootstrap-cert lifecycle on top of the per-device one.
- **Community L3 constructs (`@cdklabs/cdk-aws-iot-thing-certificate-policy`, `cdk-iot-core-certificates`).** All three persist keys to **SSM Parameter Store** (we want **Secrets Manager** for the 7-day recovery window), and `@cdklabs/...` mustache-substitutes the policy at synth time (one CFN policy per Thing, vs. our shared policy with runtime IoT variables for 17 Things). Single-maintainer experimental L3s also clash with our deprecation-currency rule.

## What

```mermaid
flowchart LR
  CDK[CDK_deploy]
  CR[CloudFormation_CustomResource]
  L["Lambda_PythonHandler"]
  IoT[IoT_Core_API]
  SM[Secrets_Manager]
  Op[Operator_or_script]
  Pi[Raspberry_Pi]

  CDK --> CR --> L --> IoT
  L --> SM
  Op -->|"GetSecretValue"| SM
  Op --> Pi
  Pi -->|"MQTT 5 mtls"| IoT
```

### Resources

| Resource                             | Source                                                                | Notes                                                                              |
| ------------------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `AWS::IoT::Thing` (per device)       | `iot.CfnThing` in the stack                                           | One per name in the `thingNames` CDK context list.                                 |
| `AWS::IoT::Policy` (one)             | `iot.CfnPolicy` in the stack                                          | Per-Thing-scoped via IoT policy variables — one CFN resource serves all 17 Things. |
| Certificate + private key            | `iot.create_keys_and_certificate(setAsActive=True)` inside the Lambda | Minted exactly once per Thing.                                                     |
| `AWS::IoT::ThingPrincipalAttachment` | `iot.attach_thing_principal` inside the Lambda                        | Bound by the handler so deletion order is under our control.                       |
| Secrets Manager secret (per device)  | `secretsmanager.create_secret` / `put_secret_value` inside the Lambda | Name: **`iot/things/<thingName>/credentials`**.                                    |
| Custom-resource Lambda + `Provider`  | Stack                                                                 | One Lambda; one CR per Thing in the loop.                                          |

### Per-Thing scoped IoT policy

```text
arn:aws:iot:us-west-2:<acct>:client/${iot:Connection.Thing.ThingName}
arn:aws:iot:us-west-2:<acct>:topic/hello/${iot:Connection.Thing.ThingName}/*
arn:aws:iot:us-west-2:<acct>:topicfilter/hello/${iot:Connection.Thing.ThingName}/*
```

The Connect resource pattern enforces `clientId == thingName` because the IoT data plane only resolves `${iot:Connection.Thing.ThingName}` for an attached cert. The `iot:Connection.Thing.IsAttached: "true"` Bool condition is a defensive belt-and-suspenders.

### Secrets Manager schema (`SecretBundle`)

```json
{
  "thingName": "hw-pi-001",
  "certificateId": "...",
  "certificateArn": "arn:aws:iot:us-west-2:...:cert/...",
  "certificatePem": "-----BEGIN CERTIFICATE-----\n...",
  "privateKey": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "iotDataEndpoint": "abc.iot.us-west-2.amazonaws.com"
}
```

The Lambda **execution role does not have `secretsmanager:GetSecretValue`** — only humans/CI with narrow IAM read PEMs. The CLI's `sbc iot fetch-credentials` is the canonical reader.

### Cert lifecycle (no orphans)

The handler and the operator CLI share **one** Python function:

[`sbc_config/modules/iot/lifecycle.py::decommission_thing`](../sbc_config/modules/iot/lifecycle.py)

| Phase      | Sequence                                                                                                                                                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Create** | `CreateKeysAndCertificate(setAsActive=True)` → `AttachPolicy` → `AttachThingPrincipal` → `CreateSecret` (or `PutSecretValue`) → return `PhysicalResourceId = certificateId`.                                                      |
| **Update** | If `CertVersion` or `ThingName` changed in the resource properties, treat as **Replace** (mints a new cert; CFN runs `Delete` on the old one). Otherwise no-op.                                                                   |
| **Delete** | `DetachThingPrincipal` → `DetachPolicy` → `UpdateCertificate(status='INACTIVE')` → `DeleteCertificate(forceDelete=False)` → `DeleteSecret(RecoveryWindowInDays=7)`. Idempotent — every step swallows `ResourceNotFoundException`. |

Tests in [`tests/test_iot_lifecycle.py`](../tests/test_iot_lifecycle.py) lock the order and idempotency.

## How

### One-time setup

```bash
uv sync --all-extras
cp .devcontainer/aws-config.example ~/.aws/config   # merge if ~/.aws/config exists; example has org SSO URL + account id
aws sso login --profile spikes-sitewise --use-device-code
export AWS_PROFILE=spikes-sitewise
aws sts get-caller-identity   # optional: expect account 867492128540
cd infra/cdk
cdk bootstrap aws://867492128540/us-west-2
```

One-time per account/region. Skip if this environment is already bootstrapped (e.g. Preston deploy used the same account + region).

### Deploy / re-deploy

```bash
cd infra/cdk
cdk synth        # validate; clean, no deprecation warnings
cdk deploy       # default thingName = hw-pi-001
```

For Phase B (17 devices) — copy `infra/cdk/cdk.context.example.json` to `cdk.context.json` and uncomment the 17-name list under `_phaseB_example`.

### On the device (Pi)

```bash
sbc iot describe-endpoint
sudo sbc iot fetch-credentials --thing-name hw-pi-001 --out-dir /etc/aws-iot
sbc iot mqtt-test --thing-name hw-pi-001
```

Resulting on-disk layout:

```text
/etc/aws-iot/
├── cas/{AmazonRootCA1.pem,AmazonRootCA2.pem,AmazonRootCA3.pem,AmazonRootCA4.pem}
├── thing-cert.pem
└── thing-private.key   (mode 0600)
```

**Why CA1–CA4?** AWS IoT serves certs from Amazon Trust Services. Starfield cross-signing ended Aug 2024 — bundling all four roots avoids surprise verification failures during root rotations.

### Decommission

```bash
sbc iot decommission-thing --thing-name hw-pi-001 --yes
sbc iot list-orphan-certs                     # audit
sbc iot list-orphan-certs --delete --yes      # cleanup leftovers (rare)
```

The CDK `cdk destroy` path runs the same `decommission_thing` function via the Lambda Delete event — there's no separate teardown logic to drift.

### MQTT 5 sample (Python, `awsiotsdk`)

`sbc iot mqtt-test` is the canonical operator entry point. The under-the-hood code, kept as a copy-paste reference for engineers writing their own publishers:

```python
from awscrt import mqtt5
from awsiot import mqtt5_client_builder

client = mqtt5_client_builder.mtls_from_path(
    endpoint=DATA_ATS_ENDPOINT,
    cert_filepath="/etc/aws-iot/thing-cert.pem",
    pri_key_filepath="/etc/aws-iot/thing-private.key",
    ca_filepath="/etc/aws-iot/cas/AmazonRootCA1.pem",
    client_id=THING_NAME,
)
client.start()
client.publish(mqtt5.PublishPacket(
    topic=f"hello/{THING_NAME}/heartbeat",
    payload=b'{"ok":true}',
    qos=mqtt5.QoS.AT_LEAST_ONCE,
))
```

`mosquitto_pub` is a laptop-side smoke check only — not the device pattern.

## Greengrass v2 forward path

When we move from "hello world" to actual deployments:

- **Reuse the same device cert.** Greengrass v2 takes the cert + key from `/etc/aws-iot/`.
- **Widen the IoT policy** with the actions Greengrass v2 needs (token exchange, MQTT, deployments) per the [AWS reference policy](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html).
- **Pi 4/5:** default to **`aws.greengrass.Nucleus` v2.17.0**.
- **Constrained devices:** **`aws.greengrass.NucleusLite` v2.5.0** (<5 MB RAM; subset of features; backwards-compatible v2 APIs).
- **Greengrass v1 is sunset** — don't reach for it. See [`.cursor/rules/aws-iot-avoid-deprecated.mdc`](../.cursor/rules/aws-iot-avoid-deprecated.mdc).

A future `IotGreengrassStack` (or extension of this stack) will land the Token Exchange role + first deployment without touching the per-Thing cert flow.

## Currency / deprecation guardrails

| Topic                    | Decision                                                                                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cert mint API            | **`CreateKeysAndCertificate`**. `CreateCertificateFromCsr` only when a future device generates its own keypair.                                                                                                                                         |
| IoT attach/detach        | **`AttachPolicy`** / **`DetachPolicy`** (target = cert ARN). Never deprecated **`AttachPrincipalPolicy`**.                                                                                                                                              |
| CDK Provider role        | **`framework_on_event_role`** (and `framework_complete_and_timeout_role` if `is_complete_handler` is set). Never the deprecated **`role`** prop.                                                                                                        |
| CDK Lambda log retention | Explicit **`aws_logs.LogGroup`** passed to `log_group=`. Never the deprecated `log_retention` shortcut (uses an SDK-call construct).                                                                                                                    |
| `aws-cdk-lib` pin        | **>= 2.200** so framework Lambdas default to **Node 22** (Node 20 EOL **2026-04-30**).                                                                                                                                                                  |
| Custom-handler runtime   | **`lambda.Runtime.PYTHON_3_13`**.                                                                                                                                                                                                                       |
| MQTT version             | **MQTT 5** preferred (SDK v2 default). 3.1.1 only when a constrained client cannot do v5.                                                                                                                                                               |
| Server CAs               | **Amazon Root CA1–CA4** bundled. Plan for CA rotation.                                                                                                                                                                                                  |
| Endpoint                 | **`iot:Data-ATS`** only.                                                                                                                                                                                                                                |
| Forbidden services       | AWS IoT Events (sunset 2026-05-20), IoT Analytics, IoT 1-Click, Fleet Hub, RoboRunner, Things Graph, Greengrass v1, Lookout for Equipment, Panorama. See [`.cursor/rules/aws-iot-avoid-deprecated.mdc`](../.cursor/rules/aws-iot-avoid-deprecated.mdc). |

## Operator escape hatch

If `sbc iot decommission-thing` ever can't finish (rare — usually a transient AWS error):

```bash
aws iot list-thing-principals --thing-name hw-pi-001
aws iot detach-thing-principal --thing-name hw-pi-001 --principal <certArn>
aws iot detach-policy --policy-name iot-hello-world --target <certArn>
aws iot update-certificate --certificate-id <id> --new-status INACTIVE
aws iot delete-certificate --certificate-id <id>
aws secretsmanager delete-secret --secret-id iot/things/hw-pi-001/credentials --recovery-window-in-days 7
```

Same sequence the Lambda runs. Keep this list in sync with `sbc_config/modules/iot/lifecycle.py::decommission_thing`.

## Cross-links

- Repo entry point: [README.md § Infrastructure / CDK](../README.md#infrastructure--cdk)
- CDK app: [`infra/cdk/README.md`](../infra/cdk/README.md)
- Org baseline: `iotea-infrastructure-identity-center` ▸ [`IDCTR-INFRA-0001`](/workspaces/iotea-infrastructure-identity-center/docs/IDCTR-INFRA-0001-aws-identity-center.md), [`IDCTR-INFRA-0002`](/workspaces/iotea-infrastructure-identity-center/docs/IDCTR-INFRA-0002-aws-identity-center-cdk.md), [`IDCTR-INFRA-0003`](/workspaces/iotea-infrastructure-identity-center/docs/IDCTR-INFRA-0003-workload-cdk-pattern.md)
- Sibling spike (devx pattern source): [`iotea-spike-preston-sitewise`](/workspaces/iotea-spike-preston-sitewise)
- Skill: [`.cursor/skills/infra-cdk/SKILL.md`](../.cursor/skills/infra-cdk/SKILL.md)
- Deprecation rule: [`.cursor/rules/aws-iot-avoid-deprecated.mdc`](../.cursor/rules/aws-iot-avoid-deprecated.mdc)
