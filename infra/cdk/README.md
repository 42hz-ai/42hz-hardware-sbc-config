# `infra/cdk/` — IoT hello-world stack

Concise operator card. Full "why / what / how" lives in [**`SBCC-INFRA-0001`**](../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md).

## Contract

|                 |                                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Stack**       | `IotHelloStack`                                                                                                        |
| **Account**     | `iotea-workloads-spikes-sitewise` (Workloads ▸ Spikes OU)                                                              |
| **Region**      | `us-west-2`                                                                                                            |
| **CLI profile** | `spikes-sitewise`                                                                                                      |
| **CDK app**     | `cdk.json` → `uv run --project ../.. python app.py` (run from this directory)                                          |
| **Resources**   | One IoT policy (per-Thing scoped via IoT vars) + N IoT Things + one custom-resource Lambda + N Secrets Manager secrets |

## Prerequisites

- `aws-cdk-lib` + `constructs` from the root `[project.optional-dependencies] cdk` extra:

  ```bash
  uv sync --extra cdk
  ```

- `aws` CLI v2 + `cdk` CLI on PATH (devcontainer's Dockerfile installs both).
- `~/.aws/config` with `[profile spikes-sitewise]` (start from [`.devcontainer/aws-config.example`](../../.devcontainer/aws-config.example)).
- Bootstrapped account: `cdk bootstrap aws://<account-id>/us-west-2` once per account.

## Deploy

```bash
aws sso login --profile spikes-sitewise --use-device-code
export AWS_PROFILE=spikes-sitewise

cd infra/cdk
cdk synth          # clean, no deprecation warnings
cdk deploy         # default: thingName=hw-pi-001
```

For 17 devices, copy [`cdk.context.example.json`](cdk.context.example.json) → `cdk.context.json`, swap to the `_phaseB_example` block, then `cdk deploy`.

## Operator commands (after deploy)

All operator workflows go through the **`sbc iot`** CLI (mirrored Python in `sbc_config/commands/iot/`):

```bash
sbc iot describe-endpoint
sudo sbc iot fetch-credentials --thing-name hw-pi-001 --out-dir /etc/aws-iot
sbc iot mqtt-test --thing-name hw-pi-001
sbc iot decommission-thing --thing-name hw-pi-001 --yes
sbc iot list-orphan-certs
```

Run `sbc iot --help` (and `sbc iot <subcommand> --help`) for flags. Each subcommand is documented inline; this README does not duplicate them so they can't drift.

## Layout

```
infra/cdk/
├── app.py                      # cdk.App() — reads thingNames from context
├── cdk.json                    # `"app": "uv run --project ../.. python app.py"`
├── cdk.context.example.json    # Phase A (1 thing) + Phase B (17 things)
├── stacks/
│   ├── __init__.py
│   └── iot_hello_stack.py      # Per-Thing-scoped policy + Provider + per-Thing CR
└── lambda/provision_device/
    ├── __init__.py
    └── handler.py              # imports sbc_config.modules.iot.lifecycle
```

## Tests

```bash
uv run python -m unittest tests.test_iot_hello_stack
uv run python -m unittest tests.test_iot_lifecycle
```

The stack snapshot test ([`tests/test_iot_hello_stack.py`](../../tests/test_iot_hello_stack.py)) catches any change that drops `${iot:Connection.Thing.ThingName}` from the policy or splits the single shared policy into per-Thing CFN resources.

## Cross-links

- [`SBCC-INFRA-0001`](../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md) — design doc + escape hatch.
- [`.cursor/skills/infra-cdk/SKILL.md`](../../.cursor/skills/infra-cdk/SKILL.md) — agent skill (CDK + CLI playbook).
- [`.cursor/rules/aws-iot-avoid-deprecated.mdc`](../../.cursor/rules/aws-iot-avoid-deprecated.mdc) — deprecation guardrail rule.
- Sibling repo: [`iotea-infrastructure-identity-center`](/workspaces/iotea-infrastructure-identity-center) — `IDCTR-INFRA-0003` workload pattern.
