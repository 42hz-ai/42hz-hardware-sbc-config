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

Runtime dependency: ``awsiotsdk`` (``iot`` extra in ``pyproject.toml``).
Install with ``uv sync --extra iot`` before starting Nucleus; no per-component
``Install`` lifecycle step is needed because Nucleus inherits the shell PATH
which puts ``.venv/bin`` first.

The process runs until Nucleus sends SIGTERM (component stop / shutdown).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time

from datetime import datetime, timezone


def main() -> None:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    thing_name = os.environ.get("AWS_IOT_THING_NAME", "unknown")
    topic = f"hello/{thing_name}/telemetry"

    # Diagnostic: printed once at startup, visible in the component log.
    sys.stdout.write(
        f"telemetry-publisher: python={sys.executable} version={sys.version_info[:2]}\n"
    )
    sys.stdout.write(f"telemetry-publisher: sys.path[0:3]={sys.path[:3]}\n")
    sys.stdout.flush()

    try:
        from awsiot.greengrasscoreipc.clientv2 import (  # noqa: PLC0415
            GreengrassCoreIPCClientV2,
        )
        from awsiot.greengrasscoreipc.model import QOS  # noqa: PLC0415
    except ImportError as exc:
        sys.stderr.write(
            f"awsiot not available — run `uv sync --extra iot` in the repo root: {exc}\n"
        )
        sys.stderr.write(f"  sys.executable={sys.executable}\n")
        sys.stderr.write(f"  sys.path={sys.path}\n")
        sys.exit(1)

    client = GreengrassCoreIPCClientV2()

    running = True

    def _stop(sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    sys.stdout.write(
        f"telemetry-publisher: starting — topic={topic}, interval={interval}s\n"
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
