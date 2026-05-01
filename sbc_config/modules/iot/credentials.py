"""Read PEM bundles from Secrets Manager and lay them out on disk.

The ``SecretBundle`` JSON shape is the contract written by the CDK
custom-resource Lambda's ``Create`` step. Same schema, both directions.
"""

from __future__ import annotations

import json
import stat

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from sbc_config.modules.iot.client import secrets_client as _secrets_client_factory

# Amazon Trust Services — published roots for AWS IoT. Mirrors AWS public docs.
# https://www.amazontrust.com/repository/
AMAZON_ROOT_CA_URLS: dict[str, str] = {
    "AmazonRootCA1.pem": "https://www.amazontrust.com/repository/AmazonRootCA1.pem",
    "AmazonRootCA2.pem": "https://www.amazontrust.com/repository/AmazonRootCA2.pem",
    "AmazonRootCA3.pem": "https://www.amazontrust.com/repository/AmazonRootCA3.pem",
    "AmazonRootCA4.pem": "https://www.amazontrust.com/repository/AmazonRootCA4.pem",
}

DEFAULT_OUT_DIR = Path("/etc/aws-iot")
CERT_FILENAME = "thing-cert.pem"
KEY_FILENAME = "thing-private.key"
ENDPOINT_FILENAME = "endpoint.txt"
CAS_SUBDIR = "cas"


@dataclass
class SecretBundle:
    """JSON shape stored in Secrets Manager (no orphan, no plaintext outputs)."""

    thing_name: str
    certificate_id: str
    certificate_arn: str
    certificate_pem: str
    private_key: str
    iot_data_endpoint: str | None = None

    @classmethod
    def from_json(cls, payload: str) -> SecretBundle:
        data: dict[str, Any] = json.loads(payload)
        return cls(
            thing_name=data["thingName"],
            certificate_id=data["certificateId"],
            certificate_arn=data["certificateArn"],
            certificate_pem=data["certificatePem"],
            private_key=data["privateKey"],
            iot_data_endpoint=data.get("iotDataEndpoint"),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "thingName": self.thing_name,
                "certificateId": self.certificate_id,
                "certificateArn": self.certificate_arn,
                "certificatePem": self.certificate_pem,
                "privateKey": self.private_key,
                "iotDataEndpoint": self.iot_data_endpoint,
            },
            indent=2,
            sort_keys=True,
        )


def fetch_secret_bundle(
    secret_id: str,
    *,
    secrets_client: Any | None = None,
) -> SecretBundle:
    """Read the secret value and parse it as a ``SecretBundle``."""
    if secrets_client is None:
        secrets_client = _secrets_client_factory()
    resp = secrets_client.get_secret_value(SecretId=secret_id)
    payload = resp.get("SecretString")
    if not payload:
        msg = f"secret {secret_id!r} has no SecretString (binary secrets not supported)"
        raise ValueError(msg)
    return SecretBundle.from_json(payload)


def write_bundle_to_disk(
    bundle: SecretBundle,
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    download_cas: bool = True,
    overwrite: bool = True,
) -> dict[str, Path]:
    """Write cert, key, CA1-CA4, and optional endpoint sidecar to ``out_dir``.

    Layout::

        out_dir/
        ├── cas/
        │   ├── AmazonRootCA1.pem
        │   ├── AmazonRootCA2.pem
        │   ├── AmazonRootCA3.pem
        │   └── AmazonRootCA4.pem
        ├── endpoint.txt          (when SecretBundle.iot_data_endpoint is set)
        ├── thing-cert.pem
        └── thing-private.key     (mode 0600)

    When ``bundle.iot_data_endpoint`` is populated, ``endpoint.txt`` is
    written alongside the PEMs (mode 0644, single newline-terminated line).
    The Pi-side Docker entrypoint reads this file so ``mqtt-test`` can run
    without ``--endpoint`` or any AWS API call on the device.

    Returns a mapping of role → path for downstream consumers.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cert_path = out_dir / CERT_FILENAME
    key_path = out_dir / KEY_FILENAME

    _write_file(cert_path, bundle.certificate_pem, mode=0o644, overwrite=overwrite)
    _write_file(key_path, bundle.private_key, mode=0o600, overwrite=overwrite)

    written: dict[str, Path] = {"certificate": cert_path, "private_key": key_path}

    if bundle.iot_data_endpoint:
        endpoint_path = out_dir / ENDPOINT_FILENAME
        _write_file(
            endpoint_path,
            bundle.iot_data_endpoint.strip() + "\n",
            mode=0o644,
            overwrite=overwrite,
        )
        written["endpoint"] = endpoint_path

    if download_cas:
        cas_dir = out_dir / CAS_SUBDIR
        cas_dir.mkdir(parents=True, exist_ok=True)
        for filename, url in AMAZON_ROOT_CA_URLS.items():
            target = cas_dir / filename
            if target.exists() and not overwrite:
                continue
            _download_pem(url, target)
            target.chmod(0o644)
        written["cas_dir"] = cas_dir
    return written


def _write_file(
    path: Path,
    contents: str,
    *,
    mode: int,
    overwrite: bool,
) -> None:
    if path.exists() and not overwrite:
        msg = f"refusing to overwrite existing file: {path}"
        raise FileExistsError(msg)
    path.write_text(contents, encoding="utf-8")
    path.chmod(stat.S_IMODE(mode))


def _download_pem(url: str, dest: Path) -> None:
    """Stream a PEM body to ``dest``. URLs are pinned to amazontrust.com only."""
    if not url.startswith("https://www.amazontrust.com/"):
        msg = f"untrusted CA download URL: {url!r}"
        raise ValueError(msg)
    with urlopen(url, timeout=60) as response:  # noqa: S310 - URL pinned above
        body = response.read()
    dest.write_bytes(body)


def remove_disk_bundle(out_dir: Path = DEFAULT_OUT_DIR) -> list[Path]:
    """Delete the cert + key (CAs are public; left in place)."""
    removed: list[Path] = []
    for name in (CERT_FILENAME, KEY_FILENAME):
        target = out_dir / name
        if target.exists():
            target.unlink()
            removed.append(target)
    return removed
