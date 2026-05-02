# 42hz hardware SBC config — docs

Naming convention: `SBCC-{PREFIX}-{NNNN}-{kebab-slug}.md`. Prefixes:

- **`INFRA`** — infrastructure, CDK, AWS, deployments.
- **`CODE`** — developer guides, ADRs, onboarding, technical how-tos.

See `.cursor/skills/doc-create/SKILL.md` for the full convention and `.cursor/rules/doc-create.mdc` for active prefixes.

## Index

| Doc                                                                                            | Purpose                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`SBCC-INFRA-0001-iot-hello-world-cdk.md`](SBCC-INFRA-0001-iot-hello-world-cdk.md)             | IoT hello-world CDK stack (Secrets Manager **`SecretBundle`**, lifecycle, MQTT policy). Includes **Portable touchpoints** — contracts to reuse if Alternative A Pi/Docker is replaced. Living doc (`infra-cdk` skill). |
| [`SBCC-INFRA-0003-greengrass-local-dev-loop.md`](SBCC-INFRA-0003-greengrass-local-dev-loop.md) | Greengrass v2 Nucleus in the devcontainer + Pi: **what / why / how**, `install-greengrass`, `greengrass-cli`, `components/` scaffold, TES + policy context.                                                            |
