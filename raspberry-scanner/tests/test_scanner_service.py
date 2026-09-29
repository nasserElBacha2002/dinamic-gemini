import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanner_service import ScannerSession, SerialLineReader


class FakeReader:
    def __init__(self) -> None:
        self.values: queue.Queue[list[str] | Exception] = queue.Queue()
        self.closed = threading.Event()

    def read(self, timeout_seconds: float) -> list[str]:
        try:
            result = self.values.get(timeout=timeout_seconds)
        except queue.Empty:
            return []
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed.set()


class BlockingReader(FakeReader):
    def __init__(self) -> None:
        super().__init__()
        self.read_entered = threading.Event()
        self.release = threading.Event()

    def read(self, timeout_seconds: float) -> list[str]:
        self.read_entered.set()
        self.release.wait(timeout=1)
        return ["stale reading"]


class ScannerSessionTests(unittest.TestCase):
    def wait_for(self, condition: object) -> None:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if condition():  # type: ignore[operator]
                return
            time.sleep(0.01)
        self.fail("condition was not met")

    def test_not_configured_does_not_start(self) -> None:
        session = ScannerSession(None)
        state = session.start()
        self.assertFalse(state["scanning"])
        self.assertEqual(state["scanner_state"], "not_configured")

    def test_start_when_already_started_keeps_one_reader(self) -> None:
        reader = FakeReader()
        calls = 0

        def factory() -> FakeReader:
            nonlocal calls
            calls += 1
            return reader

        session = ScannerSession(factory)
        session.start()
        self.wait_for(lambda: session.snapshot()["scanner_state"] == "connected")
        state = session.start()
        self.assertTrue(state["scanning"])
        self.assertEqual(calls, 1)
        session.stop()

    def test_stop_when_already_stopped_is_safe(self) -> None:
        session = ScannerSession(lambda: FakeReader())
        self.assertEqual(session.stop()["scanner_state"], "stopped")
        self.assertEqual(session.stop()["scanner_state"], "stopped")
        self.assertFalse(session.snapshot()["scanning"])

    def test_stop_then_start_discards_late_read_from_previous_reader(self) -> None:
        first = BlockingReader()
        second = FakeReader()
        readers = iter([first, second])
        session = ScannerSession(lambda: next(readers))
        session.start()
        self.assertTrue(first.read_entered.wait(timeout=1))
        session.stop()
        session.start()
        first.release.set()
        self.wait_for(lambda: session.snapshot()["scanner_state"] == "connected")
        self.assertEqual(session.snapshot()["count"], 0)
        second.values.put(["new reading"])
        self.wait_for(lambda: session.snapshot()["count"] == 1)
        self.assertEqual(session.snapshot()["readings"][0]["value"], "new reading")
        session.stop()

    def test_multiple_raw_readings_respect_memory_limit(self) -> None:
        reader = FakeReader()
        session = ScannerSession(lambda: reader, max_readings=2)
        session.start()
        reader.values.put(["ABC123", " POSITION ", "D1-raw"])
        self.wait_for(lambda: session.snapshot()["count"] == 3)
        state = session.snapshot()
        self.assertEqual([item["value"] for item in state["readings"]], ["D1-raw", " POSITION "])
        self.assertEqual(state["count"], 3)
        session.stop()

    def test_reading_policy_is_recorded_without_changing_raw_value(self) -> None:
        reader = FakeReader()
        session = ScannerSession(
            lambda: reader,
            reading_policy=lambda value: {
                "accepted": value == "accepted",
                "classification": "ITEM" if value == "accepted" else "REJECTED",
            },
        )
        session.start()
        reader.values.put(["accepted", "raw rejected"])
        self.wait_for(lambda: session.snapshot()["count"] == 2)
        readings = session.snapshot()["readings"]
        self.assertEqual(readings[0]["value"], "raw rejected")
        self.assertFalse(readings[0]["accepted"])
        self.assertTrue(readings[1]["accepted"])
        session.stop()

    def test_reading_policy_exception_is_recorded_and_reader_continues(self) -> None:
        reader = FakeReader()
        calls = 0

        def policy(value: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if value == "bad":
                raise RuntimeError("profile error")
            return {"accepted": True, "classification": "RAW"}

        session = ScannerSession(lambda: reader, reading_policy=policy)
        session.start()
        reader.values.put(["bad", "good"])
        self.wait_for(lambda: session.snapshot()["count"] == 2)
        readings = session.snapshot()["readings"]
        self.assertEqual(readings[1]["classification"], "TECHNICAL_ERROR")
        self.assertEqual(readings[0]["value"], "good")
        self.assertTrue(readings[0]["accepted"])
        self.assertEqual(calls, 2)
        session.stop()

    def test_listener_failure_is_observable_and_reader_continues(self) -> None:
        reader = FakeReader()
        observed: list[str] = []

        def listener(_reading: object) -> None:
            raise RuntimeError("capture unavailable")

        session = ScannerSession(
            lambda: reader,
            reading_listener=listener,
            listener_error_handler=lambda exc: observed.append(str(exc)),
        )
        session.start()
        reader.values.put(["one", "two"])
        self.wait_for(lambda: session.snapshot()["count"] == 2)
        self.assertIn("RuntimeError: capture unavailable", session.snapshot()["listener_error"])
        self.assertEqual(observed, ["capture unavailable", "capture unavailable"])
        session.stop()

    def test_disconnect_then_reconnects_and_reads_again(self) -> None:
        first = FakeReader()
        second = FakeReader()
        readers = iter([first, second])
        session = ScannerSession(lambda: next(readers))
        session.start()
        self.wait_for(lambda: session.snapshot()["scanner_state"] == "connected")
        first.values.put(OSError("device disconnected"))
        self.wait_for(lambda: first.closed.is_set())
        self.wait_for(lambda: session.snapshot()["scanner_state"] == "connected")
        second.values.put(["reconnected raw"])
        self.wait_for(lambda: session.snapshot()["count"] == 1)
        self.assertEqual(session.snapshot()["readings"][0]["value"], "reconnected raw")
        session.stop()

    def test_stop_closes_and_detaches_active_reader(self) -> None:
        reader = FakeReader()
        session = ScannerSession(lambda: reader)
        session.start()
        self.wait_for(lambda: session.snapshot()["scanner_state"] == "connected")
        state = session.stop()
        self.assertTrue(reader.closed.wait(timeout=1))
        self.assertFalse(state["scanning"])
        self.assertEqual(state["scanner_state"], "stopped")
        self.assertIsNone(session._reader)


class SerialLineReaderTests(unittest.TestCase):
    def reader(self) -> SerialLineReader:
        reader = object.__new__(SerialLineReader)
        reader._fd = 123
        reader._buffer = bytearray()
        return reader

    def read_chunks(self, *chunks: bytes) -> list[list[str]]:
        reader = self.reader()
        with patch("scanner_service.select.select", return_value=([123], [], [])), patch(
            "scanner_service.os.read", side_effect=chunks
        ):
            return [reader.read(0) for _ in chunks]

    def test_lf_cr_and_crlf_delimiters(self) -> None:
        self.assertEqual(self.read_chunks(b"one\ntwo\n")[0], ["one", "two"])
        self.assertEqual(self.read_chunks(b"one\rtwo\r")[0], ["one", "two"])
        self.assertEqual(self.read_chunks(b"one\r\ntwo\r\n")[0], ["one", "two"])

    def test_multiple_and_fragmented_chunks_preserve_raw_content(self) -> None:
        readings = self.read_chunks(b" first ", b" value\rsecond\nthird", b"\r\n")
        self.assertEqual(readings, [[], [" first  value", "second"], ["third"]])

    def test_invalid_utf8_uses_replacement_character(self) -> None:
        self.assertEqual(self.read_chunks(b"raw-\xff\n")[0], ["raw-\ufffd"])

    def test_eof_is_reported_as_disconnect(self) -> None:
        reader = self.reader()
        with patch("scanner_service.select.select", return_value=([123], [], [])), patch(
            "scanner_service.os.read", return_value=b""
        ):
            with self.assertRaisesRegex(ConnectionError, "reached EOF"):
                reader.read(0)

    def test_buffer_limit_clears_partial_data(self) -> None:
        reader = self.reader()
        with patch("scanner_service.select.select", return_value=([123], [], [])), patch(
            "scanner_service.os.read", return_value=b"x" * 8193
        ):
            with self.assertRaisesRegex(ValueError, "exceeds 8192"):
                reader.read(0)
        self.assertEqual(reader._buffer, bytearray())


if __name__ == "__main__":
    unittest.main()
