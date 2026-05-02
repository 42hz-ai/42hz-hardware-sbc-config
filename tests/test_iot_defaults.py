"""Tests for ``sbc_config.modules.iot.defaults`` helpers."""

from __future__ import annotations

import os
import unittest

from pathlib import Path
from unittest.mock import patch

from sbc_config.modules.iot.defaults import (
    ENV_FETCH_OUT_DIR,
    ENV_IOT_DATA_DIR,
    default_mqtt_bundle_dir,
)


class TestDefaultMqttBundleDir(unittest.TestCase):
    def test_iot_data_dir_wins(self) -> None:
        with patch.dict(
            os.environ,
            {
                ENV_IOT_DATA_DIR: "/data/aws-iot",
                ENV_FETCH_OUT_DIR: "/should/not/use/when/iot/data/set",
            },
            clear=False,
        ):
            self.assertEqual(default_mqtt_bundle_dir(), Path("/data/aws-iot"))

    def test_fetch_out_dir_when_no_iot_data_dir(self) -> None:
        fake_env = dict(os.environ)
        fake_env.pop(ENV_IOT_DATA_DIR, None)
        fake_env[ENV_FETCH_OUT_DIR] = "/nfs/pems/fetch-default"
        with patch.dict(os.environ, fake_env, clear=True):
            self.assertEqual(
                default_mqtt_bundle_dir(),
                Path("/nfs/pems/fetch-default"),
            )


if __name__ == "__main__":
    unittest.main()
