# SBC Config

SBC Config — hardware domain

## Quick start

```bash
uv sync --all-extras
pre-commit install
uv run sbc hello greet
```

The CLI uses **Click** with mirrored `commands/` and `modules/`. See `.cursor/skills/cli-structure/SKILL.md` in Cursor.

The devcontainer installs dependencies and tooling on first open.

## Infrastructure / CDK

AWS-side IoT provisioning lives in [`infra/cdk/`](infra/cdk/). One stack mints a per-Thing certificate via a custom-resource Lambda, stores the PEM bundle in Secrets Manager, and binds it to a per-Thing-scoped IoT policy. The CLI (`sbc iot`) shares the cert lifecycle code with the Lambda — see [`docs/SBCC-INFRA-0001-iot-hello-world-cdk.md`](docs/SBCC-INFRA-0001-iot-hello-world-cdk.md).

```bash
uv sync --extra cdk
cp .devcontainer/aws-config.example ~/.aws/config   # first time only
aws sso login --profile spikes-sitewise --use-device-code
export AWS_PROFILE=spikes-sitewise

cd infra/cdk
cdk synth
cdk deploy

# Then on a Pi (or a laptop with awsiotsdk):
sbc iot describe-endpoint
sudo sbc iot fetch-credentials --thing-name hw-pi-001 --out-dir /etc/aws-iot
sbc iot mqtt-test --thing-name hw-pi-001
```

`sbc iot --help` lists every operator command (`describe-endpoint`, `fetch-credentials`, `mqtt-test`, `decommission-thing`, `list-orphan-certs`).

---

This repository was generated from the [42hz.ai base Copier template](https://github.com/42hz-ai/42hz-base-project). For **GitHub setup**, **syncing template updates** with `copier update`, and Copier-related notes, read **[COPIER_README.md](COPIER_README.md)**.
