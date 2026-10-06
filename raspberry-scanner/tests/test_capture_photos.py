import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camera import CameraError, FakeCamera
from capture import CaptureError, CaptureService
from capture_session_store import CaptureSessionStore, PhotoCaptureRecord
from scanner_service import Reading


class FakeRecognition:
    def __init__(self, client_id: str = "client-a", supplier_id: str = "supplier-a") -> None:
        self.value = {
            "selection_mode": "SPECIFIC" if supplier_id else "ALL",
            "client_id": client_id,
            "supplier_id": supplier_id,
        }

    def selection(self):
        return self.value


def position_reading(sequence: int) -> Reading:
    return Reading(sequence, "json-not-exported", 0, {
        "accepted": True,
        "classification": "POSITION",
        "recognition": {"results": {"POSITION": {
            "status": "VALID",
            "source": "DINAMIC",
            "position_id": "POS1",
            "pallet": "04",
            "side": "RIGHT",
        }}},
    })


def rejected_reading(sequence: int) -> Reading:
    return Reading(sequence, "raw", 0, {"accepted": False, "classification": "REJECTED"})


class SequentialFakeCamera:
    def __init__(self, *, delay_seconds: float = 0.05, fail_on: set[int] | None = None) -> None:
        self._delay = delay_seconds
        self._fail_on = fail_on or set()
        self._calls = 0
        self._lock = threading.Lock()
        self.payloads: list[bytes] = []

    @property
    def call_count(self) -> int:
        return self._calls

    def capture_jpeg(self) -> bytes:
        import time

        with self._lock:
            self._calls += 1
            call = self._calls
        time.sleep(self._delay)
        if call in self._fail_on:
            raise CameraError("sequential_fake_failure")
        payload = bytes([0xff, 0xd8, call & 0xff, 0xff, 0xd9])
        self.payloads.append(payload)
        return payload


def build_capture(
    root: Path,
    camera,
) -> tuple[CaptureService, CaptureSessionStore, Path]:
    export_dir = root / "exports"
    store = CaptureSessionStore(root / "sessions")
    photos_root = root / "photos"
    service = CaptureService(
        FakeRecognition(),
        export_dir,
        camera=camera,
        session_store=store,
        photos_root=photos_root,
    )
    return service, store, photos_root


class CapturePhotoIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_valid_scan_triggers_camera_once(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        self.assertEqual(camera.call_count, 1)

    def test_invalid_scan_does_not_trigger_camera(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(rejected_reading(1))
        capture.wait_for_photo_pipeline_idle()
        self.assertEqual(camera.call_count, 0)

    def test_successful_capture_is_complete_with_hash(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        photos = capture.snapshot()["photos"]
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["status"], "COMPLETE")
        self.assertIsNotNone(photos[0]["photo_sha256"])
        self.assertGreater(photos[0]["photo_size_bytes"], 0)
        self.assertTrue(str(photos[0]["captured_at"]).endswith("Z"))

    def test_camera_failure_marks_photo_failed(self) -> None:
        camera = FakeCamera(fail_after=1)
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        photos = capture.snapshot()["photos"]
        self.assertEqual(photos[0]["status"], "PHOTO_FAILED")
        self.assertIsNotNone(photos[0]["error"])

    def test_distinct_scans_get_distinct_capture_photo_ids(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.record(position_reading(2))
        capture.wait_for_photo_pipeline_idle()
        ids = [p["capture_photo_id"] for p in capture.snapshot()["photos"]]
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])

    def test_sequence_numbers_are_monotonic(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        for seq in range(1, 4):
            capture.record(position_reading(seq))
        capture.wait_for_photo_pipeline_idle()
        sequences = [p["sequence_number"] for p in capture.snapshot()["photos"]]
        self.assertEqual(sequences, [1, 2, 3])

    def test_restart_continues_sequence(self) -> None:
        camera = FakeCamera()
        capture, store, photos_root = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)

        resumed = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(),
            session_store=store,
            photos_root=photos_root,
        )
        self.assertEqual(resumed.snapshot()["state"], "ACTIVE")
        resumed.record(position_reading(2))
        resumed.wait_for_photo_pipeline_idle()
        sequences = [p["sequence_number"] for p in resumed.snapshot()["photos"]]
        self.assertEqual(sequences, [1, 2])

    def test_camera_failure_does_not_leave_final_jpeg(self) -> None:
        camera = FakeCamera(fail_after=1)
        capture, _, photos_root = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        photos_dir = photos_root / session_id
        jpgs = list(photos_dir.glob("*.jpg"))
        self.assertEqual(jpgs, [])

    def test_atomic_write_removes_tmp_artifacts(self) -> None:
        camera = FakeCamera()
        capture, _, photos_root = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        photos_dir = photos_root / session_id
        self.assertFalse(any(p.name.startswith(".") for p in photos_dir.iterdir()))
        self.assertEqual(len(list(photos_dir.glob("*.jpg"))), 1)

    def test_rapid_scans_preserve_scanner_to_capture_ordering(self) -> None:
        camera = SequentialFakeCamera(delay_seconds=0.08)
        capture, _, photos_root = build_capture(self.root, camera)
        capture.start("A1")

        def worker(seq: int) -> None:
            capture.record(position_reading(seq))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        capture.wait_for_photo_pipeline_idle()

        self.assertEqual(camera.call_count, 3)
        snapshot = capture.snapshot()
        session_id = snapshot["capture_session_id"]
        assert isinstance(session_id, str)
        photos_dir = photos_root / session_id
        by_seq = sorted(snapshot["photos"], key=lambda p: p["sequence_number"])
        self.assertEqual([p["scanner_sequence"] for p in by_seq], [1, 2, 3])
        for photo in by_seq:
            path = photos_dir / str(photo["file_name"])
            self.assertTrue(path.is_file())
            data = path.read_bytes()
            self.assertEqual(data[2], photo["sequence_number"])

    def test_txt_export_flow_still_works(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("PASILLO_04")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        result = capture.finish()
        body = (self.root / "exports" / "PASILLO_04.txt").read_bytes()
        self.assertEqual(result["filename"], "PASILLO_04.txt")
        self.assertEqual(body.decode("utf-8").splitlines(), ["POSITION|POS1|04|RIGHT"])

    def test_finish_waits_for_slow_camera(self) -> None:
        camera = FakeCamera(delay_seconds=0.2)
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")

        def record_scan() -> None:
            capture.record(position_reading(1))

        thread = threading.Thread(target=record_scan)
        thread.start()
        finished = capture.finish()
        thread.join()
        self.assertEqual(finished["state"], "FINISHED")
        self.assertEqual(finished["photos"][0]["status"], "COMPLETE")
        self.assertFalse(any(p["status"] == "CAPTURING" for p in finished["photos"]))

    def test_finished_session_metadata_survives_restart(self) -> None:
        camera = FakeCamera()
        capture, store, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        captured_at = capture.snapshot()["photos"][0]["captured_at"]
        capture.finish()

        reloaded = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(),
            session_store=store,
            photos_root=self.root / "photos",
        )
        snapshot = reloaded.load_finished_session(session_id)
        assert snapshot is not None
        self.assertEqual(snapshot["state"], "FINISHED")
        self.assertEqual(snapshot["capture_session_id"], session_id)
        self.assertEqual(len(snapshot["photos"]), 1)
        self.assertEqual(snapshot["photos"][0]["captured_at"], captured_at)
        self.assertEqual(snapshot["photos"][0]["status"], "COMPLETE")

    def test_new_session_does_not_destroy_finished_session(self) -> None:
        camera = FakeCamera()
        capture, store, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_a = capture.snapshot()["capture_session_id"]
        assert isinstance(session_a, str)
        capture.finish()

        capture.start("B1")
        capture.record(position_reading(1))
        capture.wait_for_photo_pipeline_idle()
        session_b = capture.snapshot()["capture_session_id"]
        assert isinstance(session_b, str)
        self.assertNotEqual(session_a, session_b)

        persisted_a = store.load_session(session_a)
        assert persisted_a is not None
        self.assertEqual(persisted_a.state, "FINISHED")
        self.assertEqual(len(persisted_a.photos), 1)

    def test_finish_waits_when_enqueue_blocked_after_inflight_reserved(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        gate = threading.Event()
        assert capture._photo_queue is not None
        real_put = capture._photo_queue.put

        def gated_put(item) -> None:
            if item is not None:
                gate.wait(5.0)
            real_put(item)

        capture._photo_queue.put = gated_put  # type: ignore[method-assign]

        record_thread = threading.Thread(target=lambda: capture.record(position_reading(1)))
        record_thread.start()
        time.sleep(0.05)

        finish_errors: list[Exception] = []
        finish_done = threading.Event()

        def run_finish() -> None:
            try:
                capture.finish()
            except Exception as exc:
                finish_errors.append(exc)
            finally:
                finish_done.set()

        finish_thread = threading.Thread(target=run_finish)
        finish_thread.start()
        time.sleep(0.1)
        self.assertFalse(finish_done.is_set())
        self.assertEqual(finish_errors, [])
        gate.set()
        finish_thread.join(timeout=3.0)
        record_thread.join(timeout=3.0)
        self.assertTrue(finish_done.is_set())
        self.assertEqual(finish_errors, [])

    def test_persistence_failure_after_reservation_closes_pipeline(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")

        with patch.object(
            capture,
            "_persist_session_locked",
            side_effect=OSError("metadata disk failure"),
        ):
            with self.assertRaisesRegex(
                CaptureError, "capture_metadata_persistence_failed"
            ):
                capture.record(position_reading(1))

        assert capture._photo_queue is not None
        self.assertTrue(capture._photo_queue.empty())
        self.assertEqual(capture._pipeline_inflight, 0)
        self.assertIn("metadata disk failure", capture.snapshot()["error"])

        started = time.monotonic()
        with self.assertRaisesRegex(CaptureError, "capture_pipeline_fatal"):
            capture.finish()
        self.assertLess(time.monotonic() - started, 0.5)

    def test_unexpected_worker_failure_marks_pipeline_fatal(self) -> None:
        camera = FakeCamera()
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        with patch.object(capture, "_update_photo_record", side_effect=RuntimeError("boom")):
            capture.record(position_reading(1))
            time.sleep(0.3)
        with self.assertRaisesRegex(CaptureError, "capture_pipeline_fatal"):
            capture.finish()

    def test_pipeline_wait_timeout_uses_total_deadline(self) -> None:
        camera = FakeCamera(delay_seconds=0.5)
        capture, _, _ = build_capture(self.root, camera)
        capture.start("A1")
        capture.record(position_reading(1))
        started = time.monotonic()
        with self.assertRaisesRegex(CaptureError, "capture_photo_pipeline_timeout"):
            capture.wait_for_photo_pipeline_idle(timeout=0.15)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.45)

    def test_crash_recovery_marks_capturing_as_photo_failed(self) -> None:
        store = CaptureSessionStore(self.root / "sessions")
        capture, _, photos_root = build_capture(self.root, FakeCamera())
        capture.start("A1")
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        from capture_session_store import CaptureSessionState

        store.save(
            CaptureSessionState(
                capture_session_id=session_id,
                aisle_code="A1",
                state="ACTIVE",
                selection=FakeRecognition().selection(),
                started_at="2026-01-01T00:00:00Z",
                next_sequence_number=2,
                export_records=[(1, "POSITION|POS1|04|RIGHT")],
                photos=[
                    PhotoCaptureRecord(
                        capture_photo_id="photo-crash",
                        sequence_number=1,
                        scanner_sequence=1,
                        export_line="POSITION|POS1|04|RIGHT",
                        status="CAPTURING",
                        captured_at="2026-01-01T00:00:01Z",
                        file_name="0001_photo-crash.jpg",
                    )
                ],
                accepted_count=1,
            )
        )
        (photos_root / session_id).mkdir(parents=True)
        (photos_root / session_id / ".0001_photo-crash.jpg.tmp").write_bytes(b"partial")
        final_path = photos_root / session_id / "0001_photo-crash.jpg"
        final_path.write_bytes(b"\xff\xd8\xff\xd9")

        resumed = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(),
            session_store=store,
            photos_root=photos_root,
        )
        resumed.wait_for_photo_pipeline_idle()
        photos = resumed.snapshot()["photos"]
        self.assertEqual(photos[0]["status"], "PHOTO_FAILED")
        self.assertEqual(photos[0]["error"], "crash_recovery_incomplete_capture")
        self.assertFalse(
            (photos_root / session_id / ".0001_photo-crash.jpg.tmp").exists()
        )
        self.assertFalse(final_path.exists())


if __name__ == "__main__":
    unittest.main()
