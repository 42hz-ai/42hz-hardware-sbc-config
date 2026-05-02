# 42hz hardware SBC config — docs

Naming convention: `SBCC-{PREFIX}-{NNNN}-{kebab-slug}.md`. Prefixes:

- **`INFRA`** — infrastructure, CDK, AWS, deployments.
- **`CODE`** — developer guides, ADRs, onboarding, technical how-tos.

See `.cursor/skills/doc-create/SKILL.md` for the full convention and `.cursor/rules/doc-create.mdc` for active prefixes.

## Index

| Doc                                                                                                  | Purpose                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`SBCC-INFRA-0001-iot-hello-world-cdk.md`](SBCC-INFRA-0001-iot-hello-world-cdk.md)                   | IoT hello-world CDK stack (Secrets Manager **`SecretBundle`**, lifecycle, MQTT policy). Includes **Portable touchpoints** — contracts to reuse if Alternative A Pi/Docker is replaced. Living doc (`infra-cdk` skill). |
| [`SBCC-INFRA-0002-iot-core-network-it-briefing.md`](SBCC-INFRA-0002-iot-core-network-it-briefing.md) | IT / network briefing: IoT Core paths, egress policy, hostnames vs IPs, PrivateLink and TLS inspection.                                                                                                                |
