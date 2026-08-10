"""Typed multi-variant CODE_SCAN session result (coverage completeness)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.application.ports.code_scanner import CodeScanDetectionCandidate


class CodeScanStopReason(str, Enum):
    COMPLETE = "COMPLETE"
    TIMEOUT = "TIMEOUT"
    MAX_CANDIDATES = "MAX_CANDIDATES"
    DECODE_FAILURE = "DECODE_FAILURE"
    ROTATIONS_DISABLED = "ROTATIONS_DISABLED"


@dataclass(frozen=True)
class CodeScanVariantObservation:
    """Per-variant observability snapshot (no secrets / raw payloads)."""

    variant_type: str
    rotation_angle: int
    duration_ms: int
    symbols_detected_count: int
    candidate_count_after_merge: int
    timeout_remaining_ms: int | None
    original_width: int | None = None
    original_height: int | None = None
    processed_width: int | None = None
    processed_height: int | None = None
    scale_ratio: float | None = None


@dataclass(frozen=True)
class CodeScanSessionResult:
    """Outcome of ``_scan_with_variants`` including whether coverage finished."""

    candidates: tuple[CodeScanDetectionCandidate, ...]
    scan_complete: bool
    stop_reason: CodeScanStopReason
    variants_attempted: int
    variant_observations: tuple[CodeScanVariantObservation, ...] = field(default_factory=tuple)
    original_width: int | None = None
    original_height: int | None = None
    processed_width: int | None = None
    processed_height: int | None = None
    scale_ratio: float | None = None

    @property
    def partial_timeout(self) -> bool:
        return (
            not self.scan_complete
            and self.stop_reason is CodeScanStopReason.TIMEOUT
            and len(self.candidates) > 0
        )


__all__ = [
    "CodeScanSessionResult",
    "CodeScanStopReason",
    "CodeScanVariantObservation",
]
