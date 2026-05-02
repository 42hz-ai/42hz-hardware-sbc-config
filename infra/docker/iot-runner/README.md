# sbc-iot-runner — Pi MQTT field image

Docker image that runs `sbc iot mqtt-test` on a **Raspberry Pi (aarch64)** as part of the IoT hello-world spike ([SBCC-INFRA-0001](../../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md)).

This follows **Alternative A** from the project plan: the operator laptop runs `fetch-credentials` and `sync-to-pi`; the Pi only publishes MQTT. No AWS API credentials are needed on the device.

```
Laptop  ──fetch-credentials──▶  Secrets Manager
Laptop  ──sync-to-pi──────────▶  Pi ~/iot-data  (PEM bundle + endpoint.txt)
Pi      ──docker compose run───▶  mqtt-test  ──MQTT 8883 TLS──▶  IoT Core
```

---

## 1. Pi prerequisites — SSH key, then Docker Engine and Compose plugin

**SSH first:** Commands like **`install-pi-docker`** and **`sync-to-pi`** use **`ssh -o BatchMode=yes`**
(so they cannot prompt for a password). If you only have password SSH today, bootstrap your pubkey once:

```bash
export SBC_IOT_PI_SSH="hz42@192.168.8.122"
uv run sbc iot add-pi-ssh-key --dry-run    # preview
uv run sbc iot add-pi-ssh-key              # ssh-copy-id (may prompt Pi password); see --help
```

Then verify **`ssh "$SBC_IOT_PI_SSH"`** works without typing a password (or **`ssh-add`** your key passphrase).

**Preferred:** use a normal key basename so **`~/.ssh/config` is unnecessary**. Generate one if needed (same account that runs **`uv run sbc`**, often **`root`** inside a devcontainer → **`~` is `/root`**):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519   # accepts defaults; passphrase optional but then ssh-add before BatchMode jobs
uv run sbc iot add-pi-ssh-key                # publishes id_ed25519.pub by default (--public-key overrides)
```

Commands like **`sync-to-pi`** and **`install-pi-docker`** invoke plain **`ssh user@host`** with **`BatchMode=yes`** — they do **not** pass **`-i`**. OpenSSH auto-offers **`~/.ssh/id_ed25519`**, **`id_rsa`**, **`id_ecdsa`** (and **`ssh-agent`** / **`~/.ssh/config`** if present).

If you switched from an old custom keypair, remove its line from **`~/.ssh/authorized_keys`** on the Pi (optional tidy-up) and delete the old private/public files locally once **`ssh`** works without **`-i`**.

**Non-default private key basename only:** if you keep a pair under another filename, add **`IdentityFile`** (and typically **`IdentitiesOnly yes`**) under a **`Host`** block in **`~/.ssh/config`** in **the same environment** as **`uv run sbc`** — see **`ssh_config(5)`**. **`add-pi-ssh-key --public-key …`** can still install whatever **`.pub`** you choose; the private key **`ssh`** offers must match.

Stock Raspberry Pi OS images do not include Docker. Install Docker once per Pi **from your laptop**
using the repo CLI (streams Docker’s **[get.docker.com](https://get.docker.com/)** convenience
installer over SSH — see **`sbc iot install-pi-docker --help`** for the curl|sh trust notes):

```bash
# From repo root on the laptop
export SBC_IOT_PI_SSH="hz42@192.168.8.122"   # or pass --ssh
uv run sbc iot install-pi-docker --dry-run   # preview
uv run sbc iot install-pi-docker             # installs + verifies (passwordless sudo on Pi)
```

If your SSH target is host-only (`~/.ssh/config` alias), add **`--remote-user YOUR_PI_LOGIN`**.

If **`install-pi-docker`** fails with **`sudo: … password is required`**, SSH is fine — allow **NOPASSWD** sudo for your Pi user (**`visudo`** / **`/etc/sudoers.d/`**) or install Docker manually once with **`ssh -t`** and an interactive prompt.

**Auditors / alternatives:** [Docker Engine — Debian](https://docs.docker.com/engine/install/debian/),
[Linux post-install](https://docs.docker.com/engine/install/linux-postinstall/).
Use **`--skip-verify`** to omit `hello-world`; use **`--no-add-user-to-docker-group`** if you will use **`sudo docker`** / **`sudo docker compose`** only.

**Manual verify** (optional):

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

**Portable contracts:** what must stay consistent if this Pi/Docker loop is replaced — CDK Secrets schema, PEM filenames, MQTT policy/topics, **`lifecycle.py`** order — lives in **[SBCC-INFRA-0001 § Portable touchpoints](../../docs/SBCC-INFRA-0001-iot-hello-world-cdk.md#portable-touchpoints-swap-the-operational-loop)**.
