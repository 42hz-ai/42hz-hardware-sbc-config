"""Download Greengrass Nucleus and install with a partial config (CLI-only).

Not imported by the CDK Lambda asset — boto3 + local disk + subprocess only.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import zipfile

from pathlib import Path
from typing import Any
from urllib.request import urlopen

from sbc_config.modules.iot.credentials import CAS_SUBDIR, CERT_FILENAME, KEY_FILENAME
from sbc_config.modules.iot.endpoint import (
    describe_credential_provider_endpoint,
    describe_data_ats_endpoint,
)

# Official release host — downloading implies acceptance of the Greengrass license.
NUCLEUS_ZIP_URL = (
    "https://d2s8p88vqu9w66.cloudfront.net/releases/greengrass-nucleus-latest.zip"
)
NUCLEUS_VERSION_DEFAULT = "2.17.0"
GREENGRASS_DEVICE_CERT = "device.pem.crt"
GREENGRASS_PRIVATE_KEY = "private.pem.key"
GREENGRASS_ROOT_CA = "AmazonRootCA1.pem"

NUCLEUS_LAUNCHED_LOG_MARKER = "Launched Nucleus successfully"


def greengrass_root_appears_installed(greengrass_root: Path) -> bool:
    """Return True if *greengrass_root* looks like a bootstrapped Nucleus tree.

    Staging ``fetch-credentials`` PEMs into the root alone is **not** enough: we
    require directories Nucleus creates after a successful install. Use
    ``--reinstall`` to force running the installer again.
    """
    if not greengrass_root.is_dir():
        return False
    packages = greengrass_root / "packages"
    work = greengrass_root / "work"
    return packages.is_dir() or work.is_dir()


def find_greengrass_jar(extracted_dir: Path) -> Path:
    """Return path to ``Greengrass.jar`` under an extracted nucleus tree."""
    for candidate in extracted_dir.rglob("Greengrass.jar"):
        return candidate
    msg = f"Greengrass.jar not found under {extracted_dir}"
    raise FileNotFoundError(msg)


def download_nucleus_zip(dest_zip: Path, *, url: str = NUCLEUS_ZIP_URL) -> None:
    """Download the Greengrass Nucleus zip to ``dest_zip``."""
    with urlopen(url, timeout=120) as response:  # noqa: S310 — pinned AWS CDN URL
        dest_zip.write_bytes(response.read())


def extract_nucleus_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract ``zip_path`` into ``target_dir``."""
    with zipfile.ZipFile(zip_path, mode="r") as zf:
        zf.extractall(target_dir)


def stage_device_crypto(*, bundle_dir: Path, greengrass_root: Path) -> None:
    """Copy PEMs from ``fetch-credentials`` layout into ``greengrass_root``."""
    cert_src = bundle_dir / CERT_FILENAME
    key_src = bundle_dir / KEY_FILENAME
    ca_src = bundle_dir / CAS_SUBDIR / GREENGRASS_ROOT_CA
    if not cert_src.is_file():
        msg = f"missing {cert_src} — run `sbc iot fetch-credentials` first"
        raise FileNotFoundError(msg)
    if not key_src.is_file():
        msg = f"missing {key_src} — run `sbc iot fetch-credentials` first"
        raise FileNotFoundError(msg)
    if not ca_src.is_file():
        msg = f"missing {ca_src} — run `sbc iot fetch-credentials` (with CA download)"
        raise FileNotFoundError(msg)

    greengrass_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cert_src, greengrass_root / GREENGRASS_DEVICE_CERT)
    shutil.copy2(key_src, greengrass_root / GREENGRASS_PRIVATE_KEY)
    shutil.copy2(ca_src, greengrass_root / GREENGRASS_ROOT_CA)
    (greengrass_root / GREENGRASS_PRIVATE_KEY).chmod(0o600)


def read_or_resolve_data_endpoint(
    bundle_dir: Path,
    *,
    iot_client: Any | None = None,
) -> str:
    """Return iot:Data-ATS host from ``endpoint.txt`` or DescribeEndpoint."""
    sidecar = bundle_dir / "endpoint.txt"
    if sidecar.is_file():
        return sidecar.read_text(encoding="utf-8").strip()

    return describe_data_ats_endpoint(iot_client=iot_client)


def write_partial_config(
    path: Path,
    *,
    thing_name: str,
    region: str,
    tes_role_alias: str,
    iot_data_endpoint: str,
    iot_cred_endpoint: str,
    greengrass_root: Path,
    nucleus_version: str,
) -> None:
    """Write the installer ``--init-config`` YAML (partial configuration)."""
    root_s = str(greengrass_root).replace("\\", "/")
    lines = [
        "---",
        "system:",
        f'  certificateFilePath: "{root_s}/{GREENGRASS_DEVICE_CERT}"',
        f'  privateKeyPath: "{root_s}/{GREENGRASS_PRIVATE_KEY}"',
        f'  rootCaPath: "{root_s}/{GREENGRASS_ROOT_CA}"',
        f'  rootpath: "{root_s}"',
        f'  thingName: "{thing_name}"',
        "services:",
        "  aws.greengrass.Nucleus:",
        '    componentType: "NUCLEUS"',
        f'    version: "{nucleus_version}"',
        "    configuration:",
        f'      awsRegion: "{region}"',
        f'      iotRoleAlias: "{tes_role_alias}"',
        f'      iotDataEndpoint: "{iot_data_endpoint}"',
        f'      iotCredEndpoint: "{iot_cred_endpoint}"',
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_nucleus_installer(
    *,
    greengrass_jar: Path,
    init_config: Path,
    greengrass_root: Path,
    setup_system_service: bool,
    foreground: bool = False,
) -> None:
    """Invoke ``java -jar Greengrass.jar`` with the standard devcontainer flags.

    Without systemd, AWS keeps Nucleus in the foreground in the JVM, which would
    block ``subprocess.run`` forever. Unless *foreground* is true, we spawn in a
    new session, redirect installer stdout/stderr to *greengrass_root*/``sbcc-nucleus-install.log``,
    and return once that log contains ``NUCLEUS_LAUNCHED_LOG_MARKER`` (JVM keeps running).
    """
    java = shutil.which("java")
    if not java:
        msg = "java not found on PATH — install a JRE (openjdk-17-jre-headless)"
        raise RuntimeError(msg)

    root_s = str(greengrass_root)
    cmd = [
        java,
        f"-Droot={root_s}",
        "-Dlog.store=FILE",
        "-jar",
        str(greengrass_jar),
        "--init-config",
        str(init_config),
        "--component-default-user",
        "root:root",
        "--setup-system-service",
        "true" if setup_system_service else "false",
    ]

    if setup_system_service or foreground:
        subprocess.run(cmd, check=True)
        return

    log_path = greengrass_root / "sbcc-nucleus-install.log"
    greengrass_root.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    logf = log_path.open("ab", buffering=0)
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        logf.close()

    _wait_for_detached_nucleus_launch(proc, log_path, timeout_s=600.0)


def _wait_for_detached_nucleus_launch(
    proc: subprocess.Popen[bytes],
    log_path: Path,
    *,
    timeout_s: float,
) -> None:
    marker = NUCLEUS_LAUNCHED_LOG_MARKER.encode()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = log_path.read_bytes() if log_path.is_file() else b""
        if marker in data:
            return
        code = proc.poll()
        if code is not None:
            time.sleep(0.15)
            data = log_path.read_bytes() if log_path.is_file() else b""
            if marker in data:
                return
            msg = f"Nucleus installer exited with status {code}; see {log_path}"
            raise RuntimeError(msg)
        time.sleep(0.25)

    proc.terminate()
    try:
        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        proc.kill()
    msg = f"Timed out waiting for Nucleus launch line in {log_path}"
    raise TimeoutError(msg)


def install_nucleus_from_bundle(
    *,
    bundle_dir: Path,
    thing_name: str,
    region: str,
    tes_role_alias: str,
    greengrass_root: Path,
    iot_client: Any | None,
    nucleus_version: str = NUCLEUS_VERSION_DEFAULT,
    setup_system_service: bool = False,
    foreground: bool = False,
    keep_download: Path | None = None,
) -> None:
    """Download nucleus (unless ``keep_download`` points to an existing zip), extract, run installer."""
    stage_device_crypto(bundle_dir=bundle_dir, greengrass_root=greengrass_root)
    data_host = read_or_resolve_data_endpoint(bundle_dir, iot_client=iot_client)
    cred_host = describe_credential_provider_endpoint(iot_client=iot_client)

    with tempfile.TemporaryDirectory(prefix="sbcc-greengrass-") as tmp_s:
        tmp = Path(tmp_s)
        zip_path = (
            keep_download
            if keep_download and keep_download.is_file()
            else tmp / "nucleus.zip"
        )
        if not zip_path.is_file():
            download_nucleus_zip(zip_path)
        extract_dir = tmp / "extracted"
        extract_dir.mkdir()
        extract_nucleus_zip(zip_path, extract_dir)
        jar = find_greengrass_jar(extract_dir)
        init_config = tmp / "sbcc-nucleus-config.yaml"
        write_partial_config(
            init_config,
            thing_name=thing_name,
            region=region,
            tes_role_alias=tes_role_alias,
            iot_data_endpoint=data_host,
            iot_cred_endpoint=cred_host,
            greengrass_root=greengrass_root,
            nucleus_version=nucleus_version,
        )
        run_nucleus_installer(
            greengrass_jar=jar,
            init_config=init_config,
            greengrass_root=greengrass_root,
            setup_system_service=setup_system_service,
            foreground=foreground,
        )


def deploy_greengrass_cli_component(
    *,
    session: Any,
    thing_name: str,
    region: str,
    component_version: str = NUCLEUS_VERSION_DEFAULT,
) -> str:
    """Start a cloud deployment that installs ``aws.greengrass.Cli`` on the core device."""
    sts = session.client("sts", region_name=region)
    account_id = sts.get_caller_identity()["Account"]
    gg = session.client("greengrassv2", region_name=region)
    target_arn = f"arn:aws:iot:{region}:{account_id}:thing/{thing_name}"
    resp = gg.create_deployment(
        targetArn=target_arn,
        deploymentName=f"sbcc-greengrass-cli-{thing_name}",
        components={
            "aws.greengrass.Cli": {
                "componentVersion": component_version,
            },
        },
    )
    deployment_id = resp.get("deploymentId")
    if not deployment_id:
        msg = "create_deployment returned no deploymentId"
        raise RuntimeError(msg)
    return deployment_id
