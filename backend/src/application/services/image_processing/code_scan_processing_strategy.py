"""Phase 3 — deterministic per-image CODE_SCAN processing strategy.

Reads a single source asset, scans it for QR/CODE128 payloads (pyzbar via the existing
``CodeScannerPort``), parses ``internal_code|quantity`` labels, consolidates repeated
detections into one logical label, and returns an :class:`ImageProcessingResult`.

Hard constraints (no OCR, no LLM fallback, no multi-label per image):
- ONE image → at most ONE resolved position (SINGLE_ASSET scope).
- RESOLVED_INTERNAL only when exactly one valid code + positive-integer quantity.
- Missing / invalid quantity with a recoverable code → PENDING_MANUAL_REVIEW.
- No detection → UNRECOGNIZED. Ambiguity → PENDING_MANUAL_REVIEW.
- Technical problems (missing file, corrupt image, scanner unavailable, timeout) →
  FAILED_TECHNICAL.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass

from src.application.ports.code_scanner import (
    CodeScanDetectionCandidate,
    CodeScannerPort,
)
from src.application.services.image_processing.code_detection_consolidator import (
    CodeConsolidationStatus,
    CodeDetectionConsolidator,
    CodeDetectionInput,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.domain.assets.entities import SourceAsset
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)

logger = logging.getLogger(__name__)

STRATEGY_KEY = "CODE_SCAN"

_SYMBOLOGY_BY_CODE_TYPE = {
    CodeType.QR: "QR_CODE",
    CodeType.BARCODE: "CODE_128",
    CodeType.DATAMATRIX: "DATA_MATRIX",
    CodeType.UNKNOWN: "UNKNOWN",
}

_PYZBAR_SYMBOLOGY_NORMALIZE = {
    "QRCODE": "QR_CODE",
    "CODE128": "CODE_128",
    "CODE39": "CODE_39",
    "EAN13": "EAN_13",
    "EAN8": "EAN_8",
    "UPCA": "UPC_A",
    "UPCE": "UPC_E",
}


class CodeScanTimeoutError(RuntimeError):
    """Raised when scanning one asset exceeds the configured wall-clock budget."""


@dataclass
class CodeScanConfig:
    quantity_max: int
    allow_decimal_quantity: bool = False
    max_image_side: int = 2048
    timeout_seconds: int = 15
    enable_rotations: bool = True
    enable_preprocessing: bool = False
    max_variants: int = 4
    max_technical_attempts: int = 2


class CodeScanMetrics:
    """Tiny in-process counter helper (no external metrics dependency required)."""

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)


def symbology_for_candidate(candidate: CodeScanDetectionCandidate) -> str:
    meta = candidate.metadata_json or {}
    pyzbar_type = str(meta.get("pyzbar_type") or "").strip().upper()
    if pyzbar_type:
        return _PYZBAR_SYMBOLOGY_NORMALIZE.get(pyzbar_type, pyzbar_type)
    return _SYMBOLOGY_BY_CODE_TYPE.get(candidate.code_type, "UNKNOWN")


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


class SourceAssetContentReaderPort:
    """Structural port: ``read_image_bytes(asset) -> bytes``."""

    def read_image_bytes(self, asset: SourceAsset) -> bytes: ...  # pragma: no cover


class CodeScanProcessingStrategy:
    strategy_key = STRATEGY_KEY

    def __init__(
        self,
        *,
        scanner: CodeScannerPort,
        content_reader: SourceAssetContentReaderPort,
        parser: EncodedLabelPayloadParser,
        consolidator: CodeDetectionConsolidator,
        config: CodeScanConfig,
        metrics: CodeScanMetrics | None = None,
    ) -> None:
        self._scanner = scanner
        self._reader = content_reader
        self._parser = parser
        self._consolidator = consolidator
        self._config = config
        self._metrics = metrics or CodeScanMetrics()

    @property
    def metrics(self) -> CodeScanMetrics:
        return self._metrics

    @property
    def attempt_provider(self) -> str:
        """Provider label recorded on ProcessingAttempt rows for CODE_SCAN (not the job's LLM provider)."""
        return "code_scan"

    @property
    def scanner_version(self) -> str:
        return self._scanner_version()

    @property
    def attempt_model(self) -> str:
        """Model label for CODE_SCAN attempts, e.g. ``pyzbar/0.1.9`` (falls back to ``pyzbar``)."""
        version = self._scanner_version()
        return f"pyzbar/{version}" if version else "pyzbar"

    def process(
        self, context: ImageProcessingContext, asset: SourceAsset
    ) -> ImageProcessingResult:
        started = time.monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        self._metrics.increment("code_scan.assets_processed")

        try:
            content = self._reader.read_image_bytes(asset)
        except FileNotFoundError as exc:
            return self._technical(context, mode, "SOURCE_ASSET_NOT_FOUND", str(exc), started)
        except Exception as exc:  # storage/read error
            return self._technical(context, mode, "SOURCE_ASSET_READ_FAILED", str(exc), started)

        if not content:
            return self._technical(
                context, mode, "SOURCE_ASSET_EMPTY", "empty source asset content", started
            )

        try:
            candidates = self._scan_with_variants(asset, content, started)
        except CodeScanTimeoutError as exc:
            self._metrics.increment("code_scan.timeout")
            return self._technical(context, mode, "CODE_SCAN_TIMEOUT", str(exc), started)
        except Exception as exc:
            # scanner unavailable / corrupt image / decode error
            self._metrics.increment("code_scan.scanner_error")
            return self._technical(context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), started)

        detections = self._to_detection_inputs(candidates)
        consolidated = self._consolidator.consolidate(detections)

        duration_ms = int((time.monotonic() - started) * 1000)
        evidence = self._build_evidence(consolidated, detections)

        if consolidated.status is CodeConsolidationStatus.RESOLVED:
            self._metrics.increment("code_scan.resolved")
            logger.info(
                "code_scan.resolved job_id=%s asset_id=%s symbology=%s duration_ms=%s",
                context.job_id,
                context.asset_id,
                evidence.get("symbology") if evidence else None,
                duration_ms,
            )
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.RESOLVED_INTERNAL,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                internal_code=consolidated.internal_code,
                quantity=float(consolidated.quantity)
                if consolidated.quantity is not None
                else None,
                evidence=evidence,
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
                processing_duration_ms=duration_ms,
            )

        if consolidated.status in (
            CodeConsolidationStatus.NO_DETECTIONS,
            CodeConsolidationStatus.NO_VALID_CODE,
        ):
            self._metrics.increment("code_scan.unrecognized")
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                evidence=evidence,
                warnings=list(consolidated.warnings),
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
                processing_duration_ms=duration_ms,
            )

        # MISSING_QUANTITY / QUANTITY_CONFLICT / MULTIPLE_DISTINCT_CODES → manual review.
        self._metrics.increment("code_scan.manual_review")
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=mode,
            resolved_by=STRATEGY_KEY,
            internal_code=consolidated.internal_code,
            evidence=evidence,
            warnings=list(consolidated.warnings),
            error_code=consolidated.status.value,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
            processing_duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _check_timeout(self, started: float) -> None:
        if self._config.timeout_seconds <= 0:
            return
        if (time.monotonic() - started) > self._config.timeout_seconds:
            raise CodeScanTimeoutError(
                f"code scan exceeded {self._config.timeout_seconds}s budget"
            )

    def _scan_with_variants(
        self, asset: SourceAsset, content: bytes, started: float
    ) -> list[CodeScanDetectionCandidate]:
        self._check_timeout(started)
        candidates = list(self._scanner.scan_asset(asset, content))
        if candidates or not self._config.enable_rotations:
            return candidates

        # Deterministic rotation order; variant 0 already consumed above.
        rotation_angles = [90, 180, 270][: max(0, self._config.max_variants - 1)]
        for angle in rotation_angles:
            self._check_timeout(started)
            rotated = self._rotated_variant_bytes(content, angle)
            if rotated is None:
                break
            self._metrics.increment("code_scan.rotation_variant")
            candidates = list(self._scanner.scan_asset(asset, rotated))
            if candidates:
                break
        return candidates

    def _rotated_variant_bytes(self, content: bytes, angle: int) -> bytes | None:
        """Best-effort rotated (and downscaled) PNG bytes; None if undecodable here."""
        try:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(content)) as img:
                oriented = ImageOps.exif_transpose(img) or img
                oriented = oriented.convert("RGB")
                oriented = self._maybe_downscale(oriented)
                rotated = oriented.rotate(-angle, expand=True)
                buf = io.BytesIO()
                rotated.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            return None

    def _maybe_downscale(self, image):
        max_side = int(self._config.max_image_side or 0)
        if max_side <= 0:
            return image
        longest = max(image.size)
        if longest <= max_side:
            return image
        scale = max_side / float(longest)
        new_size = (max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale)))
        return image.resize(new_size)

    def _to_detection_inputs(
        self, candidates: list[CodeScanDetectionCandidate]
    ) -> list[CodeDetectionInput]:
        out: list[CodeDetectionInput] = []
        for idx, cand in enumerate(candidates):
            parsed = self._parser.parse(cand.code_value or "")
            out.append(
                CodeDetectionInput(
                    symbology=symbology_for_candidate(cand),
                    raw_value=cand.code_value or "",
                    parsed=parsed,
                    bounding_box=cand.bounding_box_json,
                    detection_index=idx,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Evidence (no raw payload; only sha256 hash)
    # ------------------------------------------------------------------

    def _build_evidence(self, consolidated, detections) -> dict | None:
        if not detections:
            return {
                "scanner_name": self._scanner_name(),
                "scanner_version": self._scanner_version(),
                "detection_count": 0,
            }
        selected_idx = consolidated.selected_detection_index
        selected = None
        if selected_idx is not None:
            selected = next(
                (d for d in detections if d.detection_index == selected_idx), None
            )
        if selected is None:
            selected = detections[0]
        return {
            "scanner_name": self._scanner_name(),
            "scanner_version": self._scanner_version(),
            "symbology": selected.symbology,
            "raw_value_hash": _sha256_hex(selected.raw_value),
            "bounding_box": selected.bounding_box,
            "detection_count": len(detections),
            "distinct_codes": len(consolidated.distinct_codes),
        }

    def _scanner_name(self) -> str:
        return str(getattr(self._scanner, "engine_name", "") or "code_scanner")

    def _scanner_version(self) -> str:
        return str(getattr(self._scanner, "engine_version", "") or "")

    def _technical(
        self,
        context: ImageProcessingContext,
        mode: str,
        code: str,
        message: str,
        started: float,
    ) -> ImageProcessingResult:
        self._metrics.increment("code_scan.failed_technical")
        logger.warning(
            "code_scan.failed_technical job_id=%s asset_id=%s error_code=%s",
            context.job_id,
            context.asset_id,
            code,
        )
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=mode,
            resolved_by=STRATEGY_KEY,
            error_code=code,
            error_message=message[:2048],
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
            processing_duration_ms=int((time.monotonic() - started) * 1000),
        )


__all__ = [
    "CodeScanConfig",
    "CodeScanMetrics",
    "CodeScanProcessingStrategy",
    "CodeScanTimeoutError",
    "STRATEGY_KEY",
    "symbology_for_candidate",
]
