"""Code scanner port — Phase 1 uses noop/fake implementations; pyzbar in Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.assets.entities import SourceAsset
from src.domain.code_scans.entities import CodeScanDetectionStatus, CodeType


@dataclass(frozen=True)
class CodeScanDetectionCandidate:
    code_type: CodeType
    code_value: str
    detection_status: CodeScanDetectionStatus = CodeScanDetectionStatus.DETECTED
    confidence: float | None = None
    bounding_box_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class CodeScannerPort(Protocol):
    """Decode QR/barcodes from a source asset. Phase 1: noop returns empty list."""

    @property
    def engine_name(self) -> str:
        """Stable engine identifier persisted on runs and detections."""
        ...

    def scan_asset(self, asset: SourceAsset, content: bytes | None = None) -> list[CodeScanDetectionCandidate]:
        """Return zero or more candidate detections for one asset."""
        ...
