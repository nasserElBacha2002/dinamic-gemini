"""Phase 4 — port for internal (local) OCR label reading.

Domain/application depend on this Protocol only — never on pytesseract / Tesseract SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class InternalOcrEngineUnavailableError(RuntimeError):
    """OCR engine binary/SDK cannot be used (missing install, bad path, etc.)."""


class InternalOcrEngineTimeoutError(RuntimeError):
    """OCR engine call exceeded a real cancellable timeout (subprocess killed)."""


class OcrVariantReadError(RuntimeError):
    """Known operational failure reading a single OCR variant (may try next variant)."""


class OcrEngineTransientError(OcrVariantReadError):
    """Transient engine/IO failure for one variant (may try next variant)."""


@dataclass(frozen=True)
class PreparedImage:
    """Preprocessed image bytes ready for the OCR engine (typically PNG/JPEG RGB)."""

    content: bytes
    width: int
    height: int
    variant_name: str
    mime_type: str = "image/png"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InternalOcrContext:
    """Per-call OCR context (no secrets; safe for logs/metrics)."""

    job_id: str
    asset_id: str
    client_id: str | None
    language: str
    timeout_seconds: float
    max_image_dimension: int
    page_segmentation_mode: int | None = None


@dataclass(frozen=True)
class OcrTextBlock:
    text: str
    confidence: float | None
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    line_num: int | None = None
    block_num: int | None = None


@dataclass(frozen=True)
class InternalOcrReadResult:
    full_text: str
    text_blocks: tuple[OcrTextBlock, ...]
    confidence: float | None
    orientation: int | None
    engine_name: str
    engine_version: str | None
    duration_ms: int
    warnings: tuple[str, ...] = ()
    raw_meta: dict[str, Any] = field(default_factory=dict)


class InternalLabelReader(Protocol):
    """Read printed label text from a prepared image using a local OCR engine."""

    @property
    def engine_name(self) -> str: ...

    @property
    def engine_version(self) -> str | None: ...

    def read(
        self,
        image: PreparedImage,
        context: InternalOcrContext,
    ) -> InternalOcrReadResult: ...


__all__ = [
    "InternalLabelReader",
    "InternalOcrContext",
    "InternalOcrEngineTimeoutError",
    "InternalOcrEngineUnavailableError",
    "InternalOcrReadResult",
    "OcrEngineTransientError",
    "OcrTextBlock",
    "OcrVariantReadError",
    "PreparedImage",
]
