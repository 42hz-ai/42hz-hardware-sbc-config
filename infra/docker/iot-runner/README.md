# sbc-iot-runner — Pi MQTT field image

Docker image that runs `sbc iot mqtt-test` on a **Raspberry Pi (aarch64)** as part of the IoT hello-world spike ([SBCC-INFRA-0001](../../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md)).

This follows **Alternative A** from the project plan: the operator laptop runs `fetch-credentials` and `sync-to-pi`; the Pi only publishes MQTT. No AWS API credentials are needed on the device.

```
Laptop  ──fetch-credentials──▶  Secrets Manager
Laptop  ──sync-to-pi──────────▶  Pi ~/iot-data  (PEM bundle + endpoint.txt)
Pi      ──docker compose run───▶  mqtt-test  ──MQTT 8883 TLS──▶  IoT Core
```

---

## 1. Pi prerequisites — Docker Engine and Compose plugin

Stock Raspberry Pi OS images do not include Docker. Install it once per Pi
following the official [Docker Engine on Debian](https://docs.docker.com/engine/install/debian/) guide (arm64):

```bash
# Remove any distro docker.io shim (harmless if absent)
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Docker apt prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Docker GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker apt repo (arm64, bookworm)
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker CE + Compose v2
sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Start and enable daemon
sudo systemctl enable --now docker
```

**Post-install — add your user to the docker group** (re-login or `newgrp docker` to apply):

```bash
sudo usermod -aG docker "$USER"
```

Alternatively, prefix all `docker` calls with `sudo` — both approaches work.

**Verify:**

```bash
docker version
docker compose version
docker run --rm hello-world
```

---

## 2. Network requirements

The Pi only needs **outbound TCP 8883** to the `iotDataEndpoint` hostname
(account- and region-specific, stored in `~/iot-data/endpoint.txt`).
See [SBCC-INFRA-0002](../../../docs/SBCC-INFRA-0002-iot-core-network-it-briefing.md).

Wired Ethernet is recommended until Wi-Fi country/rfkill is configured separately.

---

## 3. Operator runbook (laptop side)

> Prerequisites: `uv`, AWS SSO login with `spikes-sitewise` profile,
> `rsync` and `ssh` on PATH.

```bash
export AWS_PROFILE=spikes-sitewise
aws sso login

# Optional: pin env vars for a dev session
export SBC_IOT_PI_SSH="hz42@192.168.8.122"
export SBC_IOT_FETCH_OUT_DIR="aws-iot-bundle"   # keep PEMs out of /etc

# Fetch PEM bundle + endpoint.txt from Secrets Manager
uv run sbc iot fetch-credentials
# Writes: aws-iot-bundle/thing-cert.pem, thing-private.key, cas/*, endpoint.txt

# Preview the sync (no files transferred)
uv run sbc iot sync-to-pi --dry-run

# Push repo + bundle to Pi
uv run sbc iot sync-to-pi
```

All flags have sane defaults — see `sbc iot sync-to-pi --help` and `sbc iot fetch-credentials --help`.

---

## 4. Pi side — build and run

```bash
ssh hz42@192.168.8.122    # or $SBC_IOT_PI_SSH

# First time: ensure your UID is correct for key file reads
id -u   # note UID; set SBC_UID in .env if != 1000

cd ~/sbc-config/infra/docker/iot-runner

# Optional: copy and customise env
cp .env.example .env
# edit .env if needed (THING_NAME, SBC_UID, IOT_DATA_DIR)

# Build (native arm64 — builds awscrt from source; takes a few minutes first time)
docker compose build

# Publish one MQTT heartbeat
docker compose run --rm iot-runner iot mqtt-test
```

The entrypoint shim reads `~/iot-data/endpoint.txt` automatically so
`--endpoint` is not required. Pass it explicitly to override:

```bash
docker compose run --rm iot-runner iot mqtt-test \
  --endpoint abc123.iot.us-west-2.amazonaws.com
```

Other `sbc iot` commands work the same way (endpoint resolution skipped for non-mqtt-test calls):

```bash
docker compose run --rm iot-runner iot describe-endpoint
```

---

## 5. Verify in AWS

In **IoT Core → Test → MQTT test client** (account `867492128540`, region `us-west-2`), subscribe to:

```
hello/hw-pi-001/#
```

Re-run `docker compose run --rm iot-runner iot mqtt-test` and confirm a message arrives on `hello/hw-pi-001/heartbeat`.

---

## 6. Rotating credentials

After `sbc iot decommission-thing` + a new CDK deploy, re-run the laptop steps:

```bash
uv run sbc iot fetch-credentials   # pulls fresh cert/key/endpoint
uv run sbc iot sync-to-pi          # pushes updated bundle to Pi
```

No changes needed to the image.

---

## 7. Future B+C path (deferred)

When you want to run `fetch-credentials` on the Pi itself (eliminating the laptop copy step), add a `~/.aws:ro` mount to `compose.yaml`, run `aws sso login` on the Pi, and drop the `--skip-bundle` flag from `sync-to-pi` if you still want to push certs from the laptop.
