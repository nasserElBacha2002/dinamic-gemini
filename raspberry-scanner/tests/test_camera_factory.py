import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camera import (
    CameraConfigurationError,
    CameraError,
    FakeCamera,
    RpicamStillCamera,
    UnconfiguredCamera,
    build_camera_from_environment,
)


class CameraFactoryTests(unittest.TestCase):
    def test_unconfigured_modes_return_none(self) -> None:
        for mode in ("", "unconfigured", "off", "disabled"):
            with patch.dict(os.environ, {"DINAMIC_CAMERA_MODE": mode}, clear=False):
                self.assertIsNone(build_camera_from_environment())

    def test_fake_mode_returns_fake_camera(self) -> None:
        with patch.dict(os.environ, {"DINAMIC_CAMERA_MODE": "fake"}, clear=False):
            camera = build_camera_from_environment()
        self.assertIsInstance(camera, FakeCamera)

    def test_rpicam_mode_returns_rpicam_still_camera(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DINAMIC_CAMERA_MODE": "rpicam",
                "DINAMIC_CAMERA_CAPTURE_DELAY_MS": "1",
                "DINAMIC_CAMERA_PROCESS_TIMEOUT_SEC": "25",
            },
            clear=False,
        ):
            camera = build_camera_from_environment()
        self.assertIsInstance(camera, RpicamStillCamera)
        self.assertEqual(camera._capture_delay_ms, 1)
        self.assertEqual(camera._process_timeout_seconds, 25.0)

    def test_enabled_mode_returns_rpicam_still_camera(self) -> None:
        with patch.dict(os.environ, {"DINAMIC_CAMERA_MODE": "enabled"}, clear=False):
            camera = build_camera_from_environment()
        self.assertIsInstance(camera, RpicamStillCamera)

    def test_unknown_mode_raises_configuration_error(self) -> None:
        with patch.dict(os.environ, {"DINAMIC_CAMERA_MODE": "unknown-backend"}, clear=False):
            with self.assertRaises(CameraConfigurationError):
                build_camera_from_environment()

    def test_unconfigured_camera_raises_camera_error(self) -> None:
        with self.assertRaises(CameraError):
            UnconfiguredCamera().capture_jpeg()


if __name__ == "__main__":
    unittest.main()
