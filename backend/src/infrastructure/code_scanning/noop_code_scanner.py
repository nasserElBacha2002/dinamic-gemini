"""Phase 1 noop code scanner — no image decoding."""

from __future__ import annotations

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.domain.assets.entities import SourceAsset

NOOP_SCANNER_ENGINE = "noop"


class NoopCodeScanner:
    """Production Phase 1 wiring: returns no detections."""

    @property
    def engine_name(self) -> str:
        return NOOP_SCANNER_ENGINE

    def scan_asset(
        self, asset: SourceAsset, content: bytes | None = None
    ) -> list[CodeScanDetectionCandidate]:
        return []
