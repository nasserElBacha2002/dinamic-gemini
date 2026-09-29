"""Scanner session and a small POSIX serial-line reader.

The scanner transport is deliberately limited to a configured serial device that
ends each reading with LF or CR.  Values are stored and exposed as raw text;
only the transport delimiter is removed.
"""

from __future__ import annotations

import os
import select
import termios
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class ScannerReader(Protocol):
    def read(self, timeout_seconds: float) -> list[str]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Reading:
    sequence: int
    value: str
    received_at: float
    decision: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "sequence": self.sequence,
            "value": self.value,
            "received_at": self.received_at,
        }
        if self.decision is not None:
            result.update(self.decision)
        return result


class SerialLineReader:
    """Read CR/LF-delimited values from a POSIX serial device without pyserial."""

    def __init__(self, device: str, baud_rate: int) -> None:
        speed_name = f"B{baud_rate}"
        speed = getattr(termios, speed_name, None)
        if speed is None:
            raise ValueError(f"unsupported baud rate: {baud_rate}")
        self._fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        self._buffer = bytearray()
        try:
            attributes = termios.tcgetattr(self._fd)
            attributes[0] = termios.IGNPAR
            attributes[1] = 0
            attributes[2] = termios.CREAD | termios.CLOCAL | termios.CS8
            attributes[3] = 0
            attributes[4] = speed
            attributes[5] = speed
            attributes[6][termios.VMIN] = 0
            attributes[6][termios.VTIME] = 0
            termios.tcsetattr(self._fd, termios.TCSANOW, attributes)
        except Exception:
            self.close()
            raise

    def read(self, timeout_seconds: float) -> list[str]:
        ready, _, _ = select.select([self._fd], [], [], timeout_seconds)
        if not ready:
            return []
        chunk = os.read(self._fd, 1024)
        if not chunk:
            raise ConnectionError("scanner device reached EOF")
        self._buffer.extend(chunk)
        if len(self._buffer) > 8192:
            self._buffer.clear()
            raise ValueError("scanner line exceeds 8192 bytes")
        readings: list[str] = []
        while True:
            positions = [p for p in (self._buffer.find(b"\n"), self._buffer.find(b"\r")) if p >= 0]
            if not positions:
                break
            end = min(positions)
            raw_line = bytes(self._buffer[:end])
            delimiter_end = end + 1
            while delimiter_end < len(self._buffer) and self._buffer[delimiter_end] in (10, 13):
                delimiter_end += 1
            del self._buffer[:delimiter_end]
            readings.append(raw_line.decode("utf-8", errors="replace"))
        return readings

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


class ScannerSession:
    def __init__(self, reader_factory: Callable[[], ScannerReader] | None, max_readings: int = 100, reading_policy: Callable[[str], dict[str, object]] | None = None, reading_listener: Callable[[Reading], None] | None = None, listener_error_handler: Callable[[Exception], None] | None = None) -> None:
        if max_readings < 1:
            raise ValueError("max_readings must be at least 1")
        self._reader_factory = reader_factory
        self._readings: deque[Reading] = deque(maxlen=max_readings)
        self._lock = threading.Lock()
        self._reader: ScannerReader | None = None
        self._thread: threading.Thread | None = None
        self._requested = False
        self._generation = 0
        self._scanner_state = "not_configured" if reader_factory is None else "stopped"
        self._error: str | None = None
        self._sequence = 0
        self._reading_policy = reading_policy
        self._reading_listener = reading_listener
        self._listener_error_handler = listener_error_handler
        self._listener_error: str | None = None

    def start(self) -> dict[str, object]:
        with self._lock:
            if self._reader_factory is None:
                self._scanner_state = "not_configured"
                self._error = "SCANNER_DEVICE is not configured"
                return self._snapshot_locked()
            if not self._requested:
                self._requested = True
                self._generation += 1
                self._scanner_state = "waiting_for_scanner"
                self._error = None
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="scanner-reader")
                self._thread.start()
            return self._snapshot_locked()

    def stop(self) -> dict[str, object]:
        with self._lock:
            self._requested = False
            self._generation += 1
            reader = self._reader
            self._reader = None
            self._scanner_state = "stopped" if self._reader_factory else "not_configured"
            self._error = None
        if reader is not None:
            reader.close()
        return self.snapshot()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, object]:
        return {
            "scanning": self._requested,
            "scanner_state": self._scanner_state,
            "error": self._error,
            "listener_error": self._listener_error,
            "count": self._sequence,
            "readings": [reading.as_dict() for reading in reversed(self._readings)],
        }

    def _run(self) -> None:
        reader_generation = -1
        while True:
            with self._lock:
                if not self._requested:
                    return
                reader = self._reader
                generation = self._generation
            if reader is None:
                try:
                    assert self._reader_factory is not None
                    reader = self._reader_factory()
                except Exception as exc:
                    self._set_waiting_error(exc)
                    time.sleep(1)
                    continue
                with self._lock:
                    if not self._requested:
                        reader.close()
                        return
                    self._reader = reader
                    self._scanner_state = "connected"
                    self._error = None
                    reader_generation = self._generation
            try:
                values = reader.read(0.25)
            except Exception as exc:
                reader.close()
                with self._lock:
                    if self._reader is reader:
                        self._reader = None
                    if self._requested and self._generation == reader_generation:
                        self._scanner_state = "waiting_for_scanner"
                        self._error = f"{type(exc).__name__}: {exc}"
                continue
            self._record(values, reader_generation)

    def _set_waiting_error(self, exc: Exception) -> None:
        with self._lock:
            if self._requested:
                self._scanner_state = "waiting_for_scanner"
                self._error = f"{type(exc).__name__}: {exc}"

    def _record(self, values: list[str], reader_generation: int) -> None:
        if not values:
            return
        now = time.time()
        with self._lock:
            if not self._requested or self._generation != reader_generation:
                return
            for value in values:
                self._sequence += 1
                decision: dict[str, object] | None = None
                if self._reading_policy is not None:
                    try:
                        decision = self._reading_policy(value)
                    except Exception as exc:
                        decision = {
                            "accepted": False,
                            "classification": "TECHNICAL_ERROR",
                            "recognition": {"error": f"{type(exc).__name__}: {exc}"},
                        }
                reading = Reading(self._sequence, value, now, decision)
                self._readings.append(reading)
                if self._reading_listener is not None:
                    try:
                        self._reading_listener(reading)
                    except Exception as exc:
                        # A capture observer is not allowed to interrupt UART.
                        self._listener_error = f"{type(exc).__name__}: {exc}"
                        if self._listener_error_handler is not None:
                            try:
                                self._listener_error_handler(exc)
                            except Exception as handler_exc:
                                self._listener_error = (
                                    f"{type(exc).__name__}: {exc}; "
                                    f"error_handler {type(handler_exc).__name__}: {handler_exc}"
                                )
