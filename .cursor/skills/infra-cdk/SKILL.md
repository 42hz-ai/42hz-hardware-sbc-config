---
name: infra-cdk
description: >-
  Governs the IoT hello CDK app under `infra/cdk/` and the `sbc iot` CLI
  (`sbc_config/commands/iot/` mirrored by `sbc_config/modules/iot/`) for
  42hz-hardware-sbc-config (Python CDK, uv, `spikes-sitewise` workload
  profile, sibling IDCTR-INFRA-0001/0002/0003 docs). When stack resources,
  the Python custom-resource handler, the per-Thing IoT policy, the Secrets
  Manager schema, the Pi MQTT 5 sample, the Greengrass v2 forward path, the
  multi-Thing context strategy, or any `sbc iot` subcommand or its shared
  `modules/iot/lifecycle.py` spine changes, the agent must update
  `docs/SBCC-INFRA-0001-iot-hello-world-cdk.md` in the same change. Use when
  creating or editing the CDK stack, the provisioning Lambda, the IoT CLI
  commands, or changing deploy/account assumptions.
disable-model-invocation: true
---

# Infra CDK + sbc iot CLI

## Purpose

This repo contains a **CDK v2 (Python)** stack and a mirrored **`sbc iot`** Click CLI that share one Python module — `sbc_config/modules/iot/lifecycle.py` — for cert detach/inactivate/delete. The CDK custom-resource Lambda imports the same `decommission_thing` function the operator runs from the CLI, so the CFN-driven and operator-driven teardown paths can never drift.

The stack provisions:

- **One** `AWS::IoT::Policy` per stack — uses IoT policy variables (`${iot:Connection.Thing.ThingName}`) so a single CFN resource serves all Things.
- **N** `AWS::IoT::Thing` resources (parameterised by the `thingNames` CDK context list).
- A Python 3.13 Lambda + `Provider` framework that mints `CreateKeysAndCertificate`, `AttachPolicy`, `AttachThingPrincipal`, and writes the cert+key bundle to **Secrets Manager** (never CloudFormation outputs).

Canonical "why / what / how" lives in **[`SBCC-INFRA-0001`](../../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md)**.

**Cursor rule:** [`.cursor/rules/cdk-aws-metadata-strings.mdc`](../../rules/cdk-aws-metadata-strings.mdc) — ASCII-only strings in AWS-bound `description=` fields; construct ID shape.

## Living-doc stewardship clause

When editing any of the following, update **`SBCC-INFRA-0001`** in the same change:

- `infra/cdk/stacks/iot_hello_stack.py`
- `infra/cdk/lambda/provision_device/handler.py`
- The IoT policy document (resource patterns, variables, conditions).
- **Greengrass-related policy statements** — also update **`SBCC-INFRA-0003`** (see **`.cursor/skills/greengrass-local-dev/SKILL.md`**).
- The Secrets Manager JSON schema (`sbc_config/modules/iot/credentials.py::SecretBundle`).
- `sbc_config/modules/iot/lifecycle.py` (shared spine for CLI + Lambda).
- Any `sbc iot` subcommand flag or CLI surface.
- Deploy / SSO / account assumptions.
- Greengrass v2 forward-path notes.
- Multi-Thing context strategy (`thingNames`, default vs list).

## Python toolchain (uv)

CDK dependencies live in the **`cdk`** optional extra of the **root** `pyproject.toml` (one `uv.lock`). `cdk.json` runs `uv run --project ../.. python app.py` so it resolves the repo-root environment.

**Operational one-liners** (from repo root):

```bash
uv sync --all-extras
aws sso login --profile spikes-sitewise --use-device-code
export AWS_PROFILE=spikes-sitewise
cd infra/cdk
cdk synth
cdk deploy
```

## Directory layout

```
infra/cdk/
  app.py                              # CDK app entrypoint (reads `thingNames` context)
  cdk.json                            # `"app": "uv run --project ../.. python app.py"`
  cdk.context.example.json            # Phase A (1 thing) + Phase B (17 things) examples
  stacks/
    iot_hello_stack.py                # Per-Thing scoped policy + Provider + per-Thing CR
  lambda/provision_device/
    handler.py                        # Imports sbc_config.modules.iot.lifecycle
sbc_config/
  commands/iot/                       # Click commands (operator surface)
  modules/iot/                        # Shared Python (CLI + Lambda; boto3 only)
    lifecycle.py                      # decommission_thing() — single source of truth
docs/
  SBCC-INFRA-0001-iot-hello-world-cdk.md
```

## Target account

**`iotea-workloads-spikes-sitewise`** under `Workloads > Spikes OU`. Canonical CLI profile **`spikes-sitewise`**. Region **`us-west-2`**.

This is defined in the sibling repo's org baseline doc — see next section.

## Sibling repo: org baseline doc

The **`iotea-infrastructure-identity-center`** repo (sibling checkout, typically at `/workspaces/iotea-infrastructure-identity-center/`) owns the org-wide conceptual baseline:

- **`docs/IDCTR-INFRA-0001-aws-identity-center.md`** — management account, OUs, permission sets, groups, pilot/spikes accounts, runbooks.
- **`docs/IDCTR-INFRA-0002-aws-identity-center-cdk.md`** — SSO one-time setup, CLI profiles, CDK bootstrap in management account.
- **`docs/IDCTR-INFRA-0003-workload-cdk-pattern.md`** — workload-account profile (`sso_account_id`), `cdk bootstrap`, deploy flow for workload repos.

### When to update the sibling docs

**Update `IDCTR-INFRA-0001`** when CDK work here changes:

- Which **account** hosts the stack (moving out of spikes).
- **Who may deploy** (new group, different permission set).
- **SSO / permission-set assumptions** (e.g. needing a custom permission set beyond `AdministratorAccess`).
- **OU placement** (e.g. promoting from Spikes to Development).
- Any other **org-wide access** story that `IDCTR-INFRA-0001` describes.

No sibling update needed for internal IoT policy / Lambda / CLI changes that don't move accounts.

## Currency / deprecation guardrails

See `.cursor/rules/aws-iot-avoid-deprecated.mdc`. Highlights:

- `iot:AttachPolicy` / `iot:DetachPolicy` (NOT `AttachPrincipalPolicy`).
- `iot:Data-ATS` endpoint only (CA1-CA4 bundle on device).
- CDK `Provider` `framework_on_event_role` (NOT deprecated `role` prop).
- `aws_logs.LogGroup` passed to `log_group=` (NOT deprecated `log_retention`).
- Lambda runtime: `lambda.Runtime.PYTHON_3_13`.
- MQTT 5 via `awsiotsdk` (`mqtt5_client_builder.mtls_from_path`).

## Doc naming

See **[`doc-create`](../doc-create/SKILL.md)** for the full naming convention. For this repo: `SBCC-INFRA-{NNNN}-{kebab-slug}.md` and `SBCC-CODE-{NNNN}-{kebab-slug}.md`.

## Checklist (agent)

- [ ] No Unicode typography in IAM/Lambda/`CfnOutput` **description** strings (see **`cdk-aws-metadata-strings`** rule).
- [ ] CDK stack synthesizes cleanly (`cdk synth` — no deprecation warnings).
- [ ] Policy uses `${iot:Connection.Thing.ThingName}` (snapshot test in `tests/test_iot_hello_stack.py`).
- [ ] Lambda Delete path imports `sbc_config.modules.iot.lifecycle.decommission_thing` (no parallel implementation).
- [ ] **`SBCC-INFRA-0001`** updated when any of the items in _Living-doc stewardship clause_ change.
- [ ] **`docs/README.md`** updated (row added or edited for new docs).
- [ ] If **org/access** assumptions changed, **`IDCTR-INFRA-0001`** in the sibling repo updated.
- [ ] CDK Python deps live in root **`pyproject.toml [project.optional-dependencies] cdk`**; local dev: `uv sync --all-extras` (minimal / CI-only: `uv sync --extra cdk`).
