"""Greengrass component — continuous telemetry publisher via Greengrass IPC.

Publishes a heartbeat JSON payload to ``hello/<thingName>/telemetry`` every
``publishIntervalSeconds`` seconds (passed as ``argv[1]`` from the recipe
configuration variable, default 5 s).

Greengrass Nucleus injects two things this script depends on:

* ``AWS_IOT_THING_NAME`` environment variable — the core device name.
* IPC socket / SVCUID — picked up automatically by ``GreengrassCoreIPCClientV2``.

The component recipe's ``accessControl`` section authorises
``aws.greengrass#PublishToIoTCore`` on ``hello/+/telemetry`` before Nucleus
will let these publishes through to IoT Core.

Dependencies live in ``repo/.venv`` (``uv sync --extra iot``). The recipe
exports ``SBCC_REPO_ROOT`` (from ``sbccRepoRoot`` in DefaultConfiguration) on the
``Run`` line so ``publisher.py`` can prepend ``.venv/lib/pythonX.Y/site-packages``.
That is necessary because Greengrass runs lifecycle scripts under POSIX
``sh -lc``; login profiles reset ``PATH``, so relying on ``PATH`` ordering for
``.venv/bin`` alone is brittle.

The process runs until Nucleus sends SIGTERM (component stop / shutdown).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time

from datetime import datetime, timezone
from pathlib import Path


def _prepend_repo_venv_site_packages() -> None:
    """Put ``repo/.venv/lib/pythonX.Y/site-packages`` early on ``sys.path``."""
    repos: list[Path] = []

    sbcc_repo = os.environ.get("SBCC_REPO_ROOT")
    if sbcc_repo:
        repos.append(Path(sbcc_repo))

    repos.append(Path.cwd())

    cwd = Path.cwd()
    repos.extend(p for p in cwd.parents if (p / "pyproject.toml").is_file())

    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    for repo in repos:
        site = (
            repo.resolve() / ".venv" / "lib" / f"python{ver}" / "site-packages"
        ).resolve()
        if site.is_dir():
            root_s = str(site)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            return


def main() -> None:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    thing_name = os.environ.get("AWS_IOT_THING_NAME", "unknown")
    topic = f"hello/{thing_name}/telemetry"

    _prepend_repo_venv_site_packages()

    try:
        from awsiot.greengrasscoreipc.clientv2 import (  # noqa: PLC0415
            GreengrassCoreIPCClientV2,
        )
        from awsiot.greengrasscoreipc.model import QOS  # noqa: PLC0415
    except ImportError as exc:
        cwd = Path.cwd()
        repos = [cwd, *cwd.parents]

        repo_line = next((p for p in repos if (p / "pyproject.toml").is_file()), cwd)

        hinted = (
            f" cwd={cwd!s} inferred_repo={repo_line!s} "
            f"(look for {repo_line}/.venv/lib/python{sys.version_info.major}."
            f"{sys.version_info.minor}/site-packages);"
        )

        sys.stderr.write(
            f"awsiot not available ({exc}).{hinted} "
            f"ensure `uv sync --extra iot` ran. Set ``sbccRepoRoot`` "
            f"in the recipe DefaultConfiguration so SBCC_REPO_ROOT points at "
            f"your repo checkout (see SBCC-INFRA-0003).\n"
            f"  sys.executable={sys.executable}\n"
        )

        sys.exit(1)

    client = GreengrassCoreIPCClientV2()

    running = True

    def _stop(sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    sys.stdout.write(
        f"telemetry-publisher: starting topic={topic} interval={interval}s "
        f"python={sys.executable}\n"
    )
    sys.stdout.flush()

    count = 0
    while running:
        count += 1
        payload = json.dumps(
            {
                "thingName": thing_name,
                "seq": count,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            separators=(",", ":"),
        ).encode()

        client.publish_to_iot_core(
            topic_name=topic,
            qos=QOS.AT_LEAST_ONCE,
            payload=payload,
        )
        sys.stdout.write(f"published [{count}] -> {topic}\n")
        sys.stdout.flush()
        time.sleep(interval)

    sys.stdout.write("telemetry-publisher: stopped\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
