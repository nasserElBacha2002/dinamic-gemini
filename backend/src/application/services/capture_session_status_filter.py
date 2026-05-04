"""Parse comma-separated capture session status filters (shared with API query params)."""

from __future__ import annotations

from src.application.errors import CaptureSessionStatusFilterInvalidError
from src.domain.capture.entities import CaptureSessionStatus


def parse_capture_session_status_filter(raw: str | None) -> list[CaptureSessionStatus] | None:
    """Strict comma-separated ``CaptureSessionStatus`` values; rejects unknown or empty segments."""
    if raw is None or not raw.strip():
        return None
    out: list[CaptureSessionStatus] = []
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            raise CaptureSessionStatusFilterInvalidError(
                "status query parameter contains an empty segment between commas"
            )
        try:
            out.append(CaptureSessionStatus(p))
        except ValueError as exc:
            raise CaptureSessionStatusFilterInvalidError(
                f"Unknown capture session status in status filter: {part.strip()!r}"
            ) from exc
    return out
