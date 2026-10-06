import tempfile
import unittest
from pathlib import Path

import app
from app import SnapshotRepository, build_session
from config.service import ConfigService


class BuildSessionTests(unittest.TestCase):
    def test_missing_device_starts_not_configured(self) -> None:
        session = build_session(None, 9600, 100)
        state = session.snapshot()
        self.assertFalse(state["scanning"])
        self.assertEqual(state["scanner_state"], "not_configured")

    def test_empty_device_starts_not_configured(self) -> None:
        session = build_session("", 9600, 100)
        self.assertEqual(session.snapshot()["scanner_state"], "not_configured")


class AppBootstrapTests(unittest.TestCase):
    def test_main_can_construct_config_service_with_snapshot_repository(self) -> None:
        self.assertTrue(hasattr(app, "SnapshotRepository"))
        path = Path(tempfile.mkdtemp()) / "recognition-config.json"
        config_service = ConfigService(SnapshotRepository(path), None)
        self.assertEqual(config_service.status()["storage_path"], str(path))


if __name__ == "__main__":
    unittest.main()
