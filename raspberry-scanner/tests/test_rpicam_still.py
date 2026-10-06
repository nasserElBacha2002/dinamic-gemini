import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camera import CameraError, RpicamStillCamera


class RpicamStillCameraTests(unittest.TestCase):
    def test_build_command_uses_immediate_capture_not_long_preview(self) -> None:
        camera = RpicamStillCamera(capture_delay_ms=1, process_timeout_seconds=30.0)
        cmd = camera.build_command()
        self.assertIn("--immediate", cmd)
        t_index = cmd.index("-t")
        self.assertEqual(cmd[t_index + 1], "1")
        self.assertNotIn("5000", cmd)

    def test_command_missing_raises_not_found(self) -> None:
        camera = RpicamStillCamera(command="missing-rpicam-still")
        with patch("camera.shutil.which", return_value=None):
            with self.assertRaisesRegex(CameraError, "not_found"):
                camera.capture_jpeg()

    def test_subprocess_timeout_maps_to_camera_error(self) -> None:
        camera = RpicamStillCamera(process_timeout_seconds=0.01)
        with patch("camera.shutil.which", return_value="/usr/bin/rpicam-still"):
            with patch(
                "camera.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="rpicam-still", timeout=0.01),
            ):
                with self.assertRaisesRegex(CameraError, "camera_capture_timeout"):
                    camera.capture_jpeg()

    def test_nonzero_exit_maps_to_camera_error(self) -> None:
        camera = RpicamStillCamera()
        completed = MagicMock(returncode=1, stdout=b"", stderr=b"boom")
        with patch("camera.shutil.which", return_value="/usr/bin/rpicam-still"):
            with patch("camera.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(CameraError, "camera_capture_failed"):
                    camera.capture_jpeg()

    def test_invalid_jpeg_payload_raises(self) -> None:
        camera = RpicamStillCamera()
        completed = MagicMock(returncode=0, stdout=b"not-a-jpeg", stderr=b"")
        with patch("camera.shutil.which", return_value="/usr/bin/rpicam-still"):
            with patch("camera.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(CameraError, "camera_capture_invalid_jpeg"):
                    camera.capture_jpeg()


if __name__ == "__main__":
    unittest.main()
