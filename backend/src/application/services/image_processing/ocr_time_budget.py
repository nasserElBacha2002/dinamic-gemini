"""Shared wall-clock budget for INTERNAL_OCR stages."""

from __future__ import annotations

import time
from dataclasses import dataclass


class OcrBudgetExceededError(RuntimeError):
    """Raised when the shared OCR deadline is exhausted."""


@dataclass
class OcrTimeBudget:
    """Single deadline shared by label detection, light OCR, and HQ OCR."""

    total_seconds: float
    started_monotonic: float
    reserved_for_hq_ocr_seconds: float = 5.0

    @classmethod
    def start(
        cls, *, total_seconds: float, reserved_for_hq_ocr_seconds: float = 5.0
    ) -> OcrTimeBudget:
        total = max(1.0, float(total_seconds))
        reserved = max(0.0, min(total * 0.6, float(reserved_for_hq_ocr_seconds)))
        return cls(
            total_seconds=total,
            started_monotonic=time.monotonic(),
            reserved_for_hq_ocr_seconds=reserved,
        )

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    def remaining_seconds(self) -> float:
        return max(0.0, self.total_seconds - self.elapsed_seconds())

    def remaining_for_detection_seconds(self) -> float:
        """Budget left for detection/light-OCR, keeping reserve for HQ OCR."""
        return max(0.0, self.remaining_seconds() - self.reserved_for_hq_ocr_seconds)

    def remaining_for_engine_call_seconds(self) -> float:
        return max(1.0, self.remaining_seconds())

    def check(self, *, stage: str) -> None:
        if self.remaining_seconds() <= 0:
            raise OcrBudgetExceededError(f"OCR budget exhausted at stage={stage}")

    def check_detection(self, *, stage: str) -> None:
        if self.remaining_for_detection_seconds() <= 0:
            raise OcrBudgetExceededError(f"OCR detection budget exhausted at stage={stage}")


__all__ = ["OcrBudgetExceededError", "OcrTimeBudget"]
