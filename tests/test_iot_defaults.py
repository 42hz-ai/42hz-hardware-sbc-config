"""Tests for ``sbc_config.modules.iot.defaults`` helpers."""

from __future__ import annotations

import os
import unittest

from pathlib import Path
from unittest.mock import patch

from sbc_config.modules.iot.defaults import (
    ENV_FETCH_OUT_DIR,
    ENV_IOT_DATA_DIR,
    default_bundle_dir_for_thing,
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

    def test_mqtt_bundle_dir_uses_thing_subdir_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                default_mqtt_bundle_dir("hw-devcontainer-001"),
                Path("aws-iot-bundles") / "hw-devcontainer-001",
            )

    def test_default_bundle_dir_for_thing_respects_env(self) -> None:
        with patch.dict(
            os.environ,
            {ENV_FETCH_OUT_DIR: "/nfs/pems/override-thing-dir"},
            clear=False,
        ):
            self.assertEqual(
                default_bundle_dir_for_thing("any-thing"),
                Path("/nfs/pems/override-thing-dir"),
            )

    def test_default_bundle_dir_for_thing_subdir(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                default_bundle_dir_for_thing("hw-pi-001"),
                Path("aws-iot-bundles") / "hw-pi-001",
            )


if __name__ == "__main__":
    unittest.main()
