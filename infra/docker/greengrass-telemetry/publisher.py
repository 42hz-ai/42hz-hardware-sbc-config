"""Greengrass Docker component — MQTT telemetry via IPC PublishToIoTCore."""

from __future__ import annotations

import json
import os
import signal
import sys
import time

from datetime import datetime, timezone

from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import QOS


def main() -> None:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    thing_name = os.environ.get("AWS_IOT_THING_NAME", "unknown")
    topic = f"hello/{thing_name}/telemetry"
    client = GreengrassCoreIPCClientV2()

    running = True

    def _stop(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    sys.stdout.write(
        f"telemetry-publisher-docker: starting topic={topic} interval={interval}s "
        f"python={sys.executable}\n",
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

    sys.stdout.write("telemetry-publisher-docker: stopped\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
