import unittest

from app import build_session


class BuildSessionTests(unittest.TestCase):
    def test_missing_device_starts_not_configured(self) -> None:
        session = build_session(None, 9600, 100)
        state = session.snapshot()
        self.assertFalse(state["scanning"])
        self.assertEqual(state["scanner_state"], "not_configured")

    def test_empty_device_starts_not_configured(self) -> None:
        session = build_session("", 9600, 100)
        self.assertEqual(session.snapshot()["scanner_state"], "not_configured")


if __name__ == "__main__":
    unittest.main()
