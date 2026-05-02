---
name: greengrass-local-dev
description: >-
  Local AWS IoT Greengrass v2 Nucleus development in the devcontainer and on
  the Pi: `components/` recipes, `sbc iot install-greengrass`,
  `infra/cdk/stacks/iot_hello_stack.py` Greengrass IoT policy actions, CDK
  context `createGreengrassTokenExchangeRole` / `greengrassTokenExchangeRoleAlias`
  (default TES role + alias in stack), stack output `GreengrassTokenExchangeRoleAlias`,
  and Nucleus version pins in `sbc_config/modules/iot/greengrass_install.py`.
  When any of these change, update `docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md`
  in the same PR. Use when adding Greengrass components, editing install flags,
  widening GG policy, or changing the local vs Pi validation flow.
disable-model-invocation: true
---

# Greengrass local development

## Canonical doc

**[SBCC-INFRA-0003 — Greengrass v2 local dev loop](../../../docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md)** — what, why, how; prerequisites; daily `greengrass-cli` loop; Pi + Docker promotion paths.

## Living-doc stewardship clause

When editing any of the following, update **`docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md`** in the **same change**:

- `components/` — recipe layout, `ComponentName` / version, `Lifecycle`, artifact conventions.
- `sbc_config/modules/iot/greengrass_install.py` — Nucleus zip URL, **Nucleus version default**, installer `java` invocation (without systemd: **background JVM** after launch; **`sbcc-nucleus-install.log`**), `deploy_greengrass_cli_component` behavior.
- `sbc_config/commands/iot/install_greengrass.py` — CLI flags (`--foreground`, **`--reinstall`**), optional env **`SBC_IOT_GG_TES_ROLE_ALIAS`**, operator messaging.
- `infra/cdk/stacks/iot_hello_stack.py` — **Greengrass-related IoT policy** statements (Connect `client/<thing>*`, shadow/job/health topics, `greengrass:*` actions), **default TES** (IAM role + `AWS::IoT::RoleAlias`), **`CfnOutput` `GreengrassTokenExchangeRoleAlias`**, optional `AssumeRoleWithCertificate` when context **`greengrassTokenExchangeRoleAlias`** is set or TES is CDK-managed; context **`createGreengrassTokenExchangeRole`** to skip managed TES.
- `.devcontainer/Dockerfile` — **Java** package or version for Nucleus.
- `infra/cdk/cdk.json` / `cdk.context.example.json` — default **`thingNames`** (e.g. `hw-devcontainer-001`) or Greengrass context keys.

Also **`docs/README.md`** when adding a new numbered sibling doc.

## Related

- **CDK + `sbc iot` lifecycle / Secrets / hello policy** — [`infra-cdk`](../infra-cdk/SKILL.md) / **[SBCC-INFRA-0001](../../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md)**.
- **Doc naming** — [`doc-create`](../doc-create/SKILL.md).

## Checklist (agent)

- [ ] `docs/SBCC-INFRA-0003-greengrass-local-dev-loop.md` updated when any stewardship path changes.
- [ ] `IotHelloStack` synthesizes; **`tests/test_iot_hello_stack.py`** greengrass policy assertions still pass.
- [ ] `uv run ruff check` + `uv run ruff format` on touched Python.
- [ ] CDK Lambda asset still excludes **`greengrass_install.py`** (see `ignore_patterns` in `iot_hello_stack._stage_lambda_asset`).
