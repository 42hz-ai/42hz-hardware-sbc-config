# 42hz hardware SBC config — docs

Naming convention: `SBCC-{PREFIX}-{NNNN}-{kebab-slug}.md`. Prefixes:

- **`INFRA`** — infrastructure, CDK, AWS, deployments.
- **`CODE`** — developer guides, ADRs, onboarding, technical how-tos.

See `.cursor/skills/doc-create/SKILL.md` for the full convention and `.cursor/rules/doc-create.mdc` for active prefixes.

## Index

| Doc                                                                                | Purpose                                                                                                                           |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| [`SBCC-INFRA-0001-iot-hello-world-cdk.md`](SBCC-INFRA-0001-iot-hello-world-cdk.md) | IoT hello-world CDK stack (per-Thing cert + Secrets Manager + `sbc iot` CLI). Living doc — kept in sync by the `infra-cdk` skill. |
