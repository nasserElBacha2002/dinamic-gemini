"""Small camera abstraction for JPEG capture (real hardware or test doubles)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Protocol

LOGGER = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Camera could not produce a JPEG frame."""


class CameraConfigurationError(ValueError):
    """Invalid or unsupported camera configuration at process startup."""


class Camera(Protocol):
    def capture_jpeg(self) -> bytes:
        """Return a JPEG image payload."""
        ...


class UnconfiguredCamera:
    """Placeholder when no camera backend is configured."""

    def capture_jpeg(self) -> bytes:
        raise CameraError("camera_not_configured")


class FakeCamera:
    """Deterministic JPEG source for unit tests."""

    def __init__(
        self,
        *,
        payload: bytes | None = None,
        fail_after: int | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._payload = payload or _minimal_jpeg()
        self._fail_after = fail_after
        self._delay_seconds = delay_seconds
        self._calls = 0
        self._lock = __import__("threading").Lock()

    @property
    def call_count(self) -> int:
        return self._calls

    def capture_jpeg(self) -> bytes:
        import time

        with self._lock:
            self._calls += 1
            call = self._calls
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        if self._fail_after is not None and call >= self._fail_after:
            raise CameraError("fake_camera_failure")
        return self._payload


class RpicamStillCamera:
    """Capture JPEG via ``rpicam-still`` (libcamera) on Raspberry Pi OS."""

    def __init__(
        self,
        *,
        command: str = "rpicam-still",
        capture_delay_ms: int = 1,
        process_timeout_seconds: float = 30.0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self._command = command
        # ``-t`` is capture delay before shutter (ms); keep minimal for scan sync.
        self._capture_delay_ms = max(0, int(capture_delay_ms))
        self._process_timeout_seconds = max(1.0, float(process_timeout_seconds))
        self._width = width
        self._height = height

    def build_command(self) -> list[str]:
        cmd = [
            self._command,
            "-o",
            "-",
            "--encoding",
            "jpg",
            "-t",
            str(self._capture_delay_ms),
            "-n",
            "--immediate",
        ]
        if self._width is not None:
            cmd.extend(["--width", str(self._width)])
        if self._height is not None:
            cmd.extend(["--height", str(self._height)])
        return cmd

    def capture_jpeg(self) -> bytes:
        if shutil.which(self._command) is None:
            raise CameraError(f"{self._command}_not_found")
        cmd = self.build_command()
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                timeout=self._process_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CameraError("camera_capture_timeout") from exc
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            raise CameraError(
                f"camera_capture_failed: exit={completed.returncode} {stderr[:200]}"
            )
        data = completed.stdout or b""
        if len(data) < 4 or not data.startswith(b"\xff\xd8"):
            raise CameraError("camera_capture_invalid_jpeg")
        return data


def build_camera_from_environment() -> Camera | None:
    """Return a camera instance from ``DINAMIC_CAMERA_MODE`` or ``None`` when disabled."""
    mode = (os.environ.get("DINAMIC_CAMERA_MODE") or "unconfigured").strip().lower()
    if mode in {"", "unconfigured", "off", "disabled"}:
        return None
    if mode == "fake":
        return FakeCamera()
    if mode in {"rpicam", "libcamera", "enabled", "on"}:
        capture_delay_ms = int(os.environ.get("DINAMIC_CAMERA_CAPTURE_DELAY_MS", "1"))
        process_timeout = float(os.environ.get("DINAMIC_CAMERA_PROCESS_TIMEOUT_SEC", "30"))
        width_raw = (os.environ.get("DINAMIC_CAMERA_WIDTH") or "").strip()
        height_raw = (os.environ.get("DINAMIC_CAMERA_HEIGHT") or "").strip()
        width = int(width_raw) if width_raw else None
        height = int(height_raw) if height_raw else None
        command = (os.environ.get("DINAMIC_CAMERA_COMMAND") or "rpicam-still").strip()
        return RpicamStillCamera(
            command=command,
            capture_delay_ms=capture_delay_ms,
            process_timeout_seconds=process_timeout,
            width=width,
            height=height,
        )
    raise CameraConfigurationError(f"unsupported DINAMIC_CAMERA_MODE: {mode!r}")


def _minimal_jpeg() -> bytes:
    return b"\xff\xd8\xff\xd9"
