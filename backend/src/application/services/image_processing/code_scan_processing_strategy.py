"""Phase 3 — deterministic per-image CODE_SCAN processing strategy.

Reads a single source asset, scans it for QR/CODE128 payloads (pyzbar via the existing
``CodeScannerPort``), parses ``internal_code|quantity`` labels, consolidates repeated
detections into one logical label, and returns an :class:`ImageProcessingResult`.

Hard constraints (no OCR, no LLM fallback):
- Position labels remain separate (Phase 3 position detection); ≥2 VALID positions → ambiguous.
- Product labels (format D1): ONE image → 0..N physical products (dedupe by label_id).
- Legacy PIPE/DI1 without label_id: at most ONE logical product (prior semantics).
- RESOLVED_INTERNAL when ≥1 valid product with positive-integer quantity.
- Missing / invalid quantity with a recoverable code → PENDING_MANUAL_REVIEW.
- No detection → UNRECOGNIZED. Ambiguity → PENDING_MANUAL_REVIEW.
- Technical problems (missing file, corrupt image, scanner unavailable, timeout) →
  FAILED_TECHNICAL.

Supplier extraction-profile / OCR validation rules (exact_length, anchors, charset for
printed text, etc.) apply only to INTERNAL_OCR. CODE_SCAN uses the deterministic
parser + consolidator. External AI (Gemini, etc.) uses prompts, not OCR profile rules.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

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
from src.application.services.image_processing.processing_event_publisher import (
    ProcessingEventPublisher,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.product_labels.format import parse_product_label_payload
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)
from src.domain.assets.entities import SourceAsset
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.infrastructure.code_scanning.image_decode import (
    UnreadableImageError,
    UnsupportedImageFormatError,
)
from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarUnavailableError

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


def _float_if_present(value: Any) -> float | None:
    return float(value) if value is not None else None


class CodeScanTimeoutError(RuntimeError):
    """Raised when scanning one asset exceeds the configured wall-clock budget."""


class CodeScannerUnavailableError(RuntimeError):
    """Raised when the barcode/QR scanner backend cannot be loaded."""


class CodeScannerDecodeError(RuntimeError):
    """Raised when the scanner fails to decode an otherwise readable image."""


class InvalidImageError(ValueError):
    """Raised when image bytes are corrupt or an unsupported format."""


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
    max_candidates_per_asset: int = 12


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

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        raise NotImplementedError


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
        event_publisher: ProcessingEventPublisher | None = None,
        position_detection=None,
        issued_label_resolver: IssuedProductLabelResolver | None = None,
    ) -> None:
        self._scanner = scanner
        self._reader = content_reader
        self._parser = parser
        self._consolidator = consolidator
        self._config = config
        self._metrics = metrics or CodeScanMetrics()
        self._events = event_publisher
        self._position_detection = position_detection
        self._issued_label_resolver = issued_label_resolver

    def _publish_asset_event(
        self,
        context: ImageProcessingContext,
        event_type: str,
        *,
        message: str | None = None,
        error_code: str | None = None,
        metadata: dict | None = None,
        severity: str = "INFO",
    ) -> None:
        if self._events is None:
            return
        try:
            self._events.publish(
                job_id=context.job_id,
                asset_id=context.asset_id,
                event_type=event_type,
                strategy=STRATEGY_KEY,
                severity=severity,
                message=message,
                error_code=error_code,
                metadata=metadata,
            )
        except Exception:
            self._metrics.increment("code_scan.event_publish_failed")
            logger.warning(
                "code_scan.asset_event_publish_failed job_id=%s asset_id=%s event=%s",
                context.job_id,
                context.asset_id,
                event_type,
                exc_info=True,
            )

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

    def process(self, context: ImageProcessingContext, asset: SourceAsset) -> ImageProcessingResult:
        started = time.monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        self._metrics.increment("code_scan.assets_processed")
        self._publish_asset_event(
            context,
            "code_scan.asset_started",
            message="CODE_SCAN asset processing started",
            metadata={"asset_id": context.asset_id},
        )

        try:
            content = self._reader.read_image_bytes(asset)
        except FileNotFoundError as exc:
            result = self._technical(context, mode, "SOURCE_ASSET_NOT_FOUND", str(exc), started)
            self._finalize_asset_event(context, result)
            return result
        except (OSError, ValueError) as exc:
            # ValueError: missing storage_key / empty object from content reader.
            result = self._technical(context, mode, "SOURCE_ASSET_READ_FAILED", str(exc), started)
            self._finalize_asset_event(context, result)
            return result

        if not content:
            result = self._technical(
                context, mode, "SOURCE_ASSET_EMPTY", "empty source asset content", started
            )
            self._finalize_asset_event(context, result)
            return result

        self._publish_asset_event(
            context,
            "asset.source_loaded",
            message="source asset bytes loaded",
            metadata={"byte_length": len(content)},
        )
        self._publish_asset_event(
            context,
            "code_scan.decode_started",
            message="barcode/QR decode started",
        )

        try:
            candidates = self._scan_with_variants(asset, content, started)
        except CodeScanTimeoutError as exc:
            self._metrics.increment("code_scan.timeout")
            self._publish_asset_event(
                context,
                "code_scan.decode_failed",
                message="CODE_SCAN timeout",
                error_code="CODE_SCAN_TIMEOUT",
                severity="ERROR",
            )
            result = self._technical(context, mode, "CODE_SCAN_TIMEOUT", str(exc), started)
            self._finalize_asset_event(context, result)
            return result
        except (PyzbarUnavailableError, CodeScannerUnavailableError) as exc:
            self._metrics.increment("code_scan.scanner_unavailable")
            self._publish_asset_event(
                context,
                "code_scan.decode_failed",
                message="CODE_SCAN scanner unavailable",
                error_code="CODE_SCAN_SCANNER_ERROR",
                severity="ERROR",
                metadata={"error_type": type(exc).__name__},
            )
            result = self._technical(context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), started)
            self._finalize_asset_event(context, result)
            return result
        except (
            UnreadableImageError,
            UnsupportedImageFormatError,
            InvalidImageError,
        ) as exc:
            self._metrics.increment("code_scan.invalid_image")
            self._publish_asset_event(
                context,
                "code_scan.decode_failed",
                message="CODE_SCAN invalid image",
                error_code="CODE_SCAN_SCANNER_ERROR",
                severity="ERROR",
                metadata={"error_type": type(exc).__name__},
            )
            result = self._technical(context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), started)
            self._finalize_asset_event(context, result)
            return result
        except (CodeScannerDecodeError, ValueError) as exc:
            # pyzbar_code_scanner raises ValueError for decode failures.
            self._metrics.increment("code_scan.scanner_error")
            self._publish_asset_event(
                context,
                "code_scan.decode_failed",
                message="CODE_SCAN decoder error",
                error_code="CODE_SCAN_SCANNER_ERROR",
                severity="ERROR",
                metadata={"error_type": type(exc).__name__},
            )
            result = self._technical(context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), started)
            self._finalize_asset_event(context, result)
            return result

        symbol_count = len(candidates)
        self._publish_asset_event(
            context,
            "code_scan.decode_completed",
            message="barcode/QR decode completed",
            metadata={"symbol_count": symbol_count},
            error_code="NO_CODE_SYMBOL_FOUND" if symbol_count == 0 else None,
        )
        if symbol_count > 0:
            self._publish_asset_event(
                context,
                "code_scan.symbols_detected",
                message="symbols detected",
                metadata={"symbol_count": symbol_count},
            )

        item_candidates = candidates
        position_meta: dict | None = None
        if self._position_detection is not None:
            position_started = time.monotonic()
            try:
                from src.application.use_cases.position_label_detection.detect_image_position_labels import (
                    ImagePositionDetectionCommand,
                )
                from src.domain.position_label_detection.entities import DetectedCode

                client_id = (context.client_id or "").strip()
                if not client_id:
                    self._metrics.increment("position_label_detection_context_invalid_total")
                    logger.info(
                        "position_label_detection_context_invalid job_id=%s asset_id=%s "
                        "code=POSITION_LABEL_DETECTION_CONTEXT_INVALID",
                        context.job_id,
                        context.asset_id,
                    )
                    position_meta = {
                        "position_detection_count": 0,
                        "position_ambiguous": False,
                        "position_statuses": ["DETECTION_CONTEXT_INVALID"],
                        "position_detection_duration_ms": int(
                            (time.monotonic() - position_started) * 1000
                        ),
                    }
                else:
                    detected_codes = [
                        DetectedCode(
                            symbology=symbology_for_candidate(c),
                            raw_value=c.code_value,
                            normalized_value=(c.code_value or "").strip(),
                            bounding_box=c.bounding_box_json,
                            confidence=c.confidence,
                            rotation_degrees=_float_if_present(
                                c.metadata_json.get("rotation_degrees")
                                if c.metadata_json is not None
                                else None
                            ),
                            candidate_index=idx,
                        )
                        for idx, c in enumerate(candidates)
                    ]
                    pos_result = self._position_detection.execute(
                        ImagePositionDetectionCommand(
                            client_id=client_id,
                            inventory_id=context.inventory_id,
                            job_id=context.job_id,
                            source_asset_id=context.asset_id,
                            codes=detected_codes,
                            client_image_id=getattr(asset, "upload_client_file_id", None),
                            ordered_capture_session_id=getattr(
                                asset, "ordered_capture_session_id", None
                            ),
                            sequence_number=getattr(asset, "sequence_number", None),
                            correlation_id=context.job_id,
                        )
                    )
                    position_indexes = set(pos_result.position_candidate_indexes)
                    # Exclude only POSITION candidates by stable index — never by raw_value alone.
                    if pos_result.disabled or pos_result.context_invalid:
                        item_candidates = candidates
                    else:
                        item_candidates = [
                            c
                            for idx, c in enumerate(candidates)
                            if idx not in position_indexes
                        ]
                    position_duration_ms = int((time.monotonic() - position_started) * 1000)
                    position_meta = {
                        "position_detection_count": len(pos_result.detections),
                        "position_ambiguous": pos_result.ambiguous,
                        "position_statuses": [
                            d.detection_status.value for d in pos_result.detections
                        ],
                        "position_detection_duration_ms": position_duration_ms,
                        "position_candidate_indexes": list(
                            pos_result.position_candidate_indexes
                        ),
                    }
                    self._metrics.increment("position_label_detection_total")
                    self._metrics.increment(
                        "position_label_detection_duration", amount=position_duration_ms
                    )
                    if any(d.detection_status.value == "VALID" for d in pos_result.detections):
                        self._metrics.increment("position_label_detection_valid_total")
                    if pos_result.ambiguous:
                        self._metrics.increment("position_label_detection_ambiguous_total")
                    if any(
                        d.detection_status.value == "CLIENT_MISMATCH"
                        for d in pos_result.detections
                    ):
                        self._metrics.increment("position_label_client_mismatch_total")
                    if any(
                        d.detection_status.value
                        in (
                            "INVALID_SIGNATURE",
                            "CLIENT_MISMATCH",
                            "LABEL_INVALIDATED",
                            "LABEL_NOT_FOUND",
                            "UNSUPPORTED_VERSION",
                            "UNSUPPORTED_LEGACY_PAYLOAD",
                            "MISSING_SIGNATURE",
                            "PAYLOAD_TOO_LARGE",
                            "SIGNATURE_VALIDATION_SKIPPED",
                        )
                        for d in pos_result.detections
                    ):
                        self._metrics.increment("position_label_detection_invalid_total")
            except Exception:
                # Position detection must not cancel item CODE_SCAN.
                self._metrics.increment("position_label_detection_failed_total")
                logger.exception(
                    "position_label_detection_failed job_id=%s asset_id=%s",
                    context.job_id,
                    context.asset_id,
                )
                item_candidates = candidates

        detections = self._to_detection_inputs(item_candidates)
        consolidated = self._consolidator.consolidate(detections)

        duration_ms = int((time.monotonic() - started) * 1000)
        evidence = self._build_evidence(consolidated, detections)
        if position_meta:
            evidence = {**(evidence or {}), "position_label_detection": position_meta}
        # Never apply OCR/supplier text-profile validation here. Profile rules are for
        # INTERNAL_OCR; AI fallback uses prompts. CODE_SCAN is consolidator-only.

        product_results, evidence, registry_hard_fail = self._resolve_issued_products(
            context=context,
            consolidated=consolidated,
            evidence=evidence,
            duration_ms=duration_ms,
            mode=mode,
        )
        if registry_hard_fail is not None:
            self._finalize_asset_event(context, registry_hard_fail)
            return registry_hard_fail

        if consolidated.status in (
            CodeConsolidationStatus.RESOLVED,
            CodeConsolidationStatus.RESOLVED_MULTI,
        ):
            # D1 path: consolidator produced product_results that must pass registry.
            if consolidated.product_results and not product_results:
                consolidated = type(consolidated)(
                    status=CodeConsolidationStatus.NO_VALID_CODE,
                    warnings=tuple(
                        list(consolidated.warnings) + ("NO_VALID_ISSUED_PRODUCT_LABEL",)
                    ),
                    rejections=consolidated.rejections,
                    product_results=(),
                )
            elif product_results or not consolidated.product_results:
                self._metrics.increment("code_scan.resolved")
                if len(product_results) > 1:
                    self._metrics.increment("multi_product_image_total")
                counted = len(product_results) if product_results else 1
                self._metrics.increment("product_labels_valid_total", amount=counted)
                logger.info(
                    "code_scan.resolved job_id=%s asset_id=%s symbology=%s "
                    "product_count=%s duration_ms=%s",
                    context.job_id,
                    context.asset_id,
                    evidence.get("symbology") if evidence else None,
                    counted,
                    duration_ms,
                )
                primary_code = (
                    product_results[0].internal_code
                    if product_results
                    else consolidated.internal_code
                )
                primary_qty = (
                    product_results[0].quantity
                    if product_results
                    else consolidated.quantity
                )
                result = ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=ImageResultStatus.RESOLVED_INTERNAL,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    internal_code=primary_code,
                    quantity=float(primary_qty) if primary_qty is not None else None,
                    evidence=evidence,
                    warnings=list(consolidated.warnings),
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                    processing_duration_ms=duration_ms,
                    product_results=list(product_results),
                )
                self._publish_asset_event(
                    context,
                    "code_scan.validation_completed",
                    message="consolidator validation completed",
                    metadata={
                        "status": ImageResultStatus.RESOLVED_INTERNAL.value,
                        "product_count": counted,
                    },
                )
                self._finalize_asset_event(context, result)
                return result

        if consolidated.status in (
            CodeConsolidationStatus.NO_DETECTIONS,
            CodeConsolidationStatus.NO_VALID_CODE,
        ):
            position_only = bool(
                position_meta
                and position_meta.get("position_candidate_indexes")
                and not item_candidates
                and consolidated.status is CodeConsolidationStatus.NO_DETECTIONS
            )
            # Position QR(s) consumed by Phase 3 — not a product-code miss; do not drive
            # GLOBAL_EXTERNAL_FALLBACK with a misleading NO_CODE_SYMBOL_FOUND.
            if position_only and position_meta is not None:
                statuses = position_meta.get("position_statuses") or []
                position_ok = any(
                    s in ("VALID", "SIGNATURE_VALIDATION_SKIPPED") for s in statuses
                )
                error_code = (
                    "POSITION_LABEL_ONLY"
                    if position_ok
                    else "POSITION_LABEL_UNRESOLVED"
                )
                self._metrics.increment("code_scan.position_only")
                result = ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=ImageResultStatus.UNRECOGNIZED,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    evidence=evidence,
                    warnings=list(consolidated.warnings),
                    error_code=error_code,
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                    processing_duration_ms=duration_ms,
                )
                self._finalize_asset_event(context, result)
                return result

            self._metrics.increment("code_scan.unrecognized")
            result = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                evidence=evidence,
                warnings=list(consolidated.warnings),
                error_code="NO_CODE_SYMBOL_FOUND",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
                processing_duration_ms=duration_ms,
            )
            self._finalize_asset_event(context, result)
            return result

        # MISSING_QUANTITY / QUANTITY_CONFLICT / MULTIPLE_DISTINCT_CODES → manual review.
        self._metrics.increment("code_scan.manual_review")
        result = ImageProcessingResult(
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
        self._finalize_asset_event(context, result)
        return result

    def _finalize_asset_event(
        self, context: ImageProcessingContext, result: ImageProcessingResult
    ) -> None:
        status = getattr(result.status, "value", str(result.status))
        self._publish_asset_event(
            context,
            "code_scan.asset_finalized",
            message="CODE_SCAN asset finalized",
            error_code=result.error_code,
            metadata={"status": status},
            severity="ERROR" if result.status is ImageResultStatus.FAILED_TECHNICAL else "INFO",
        )

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _check_timeout(self, started: float) -> None:
        if self._config.timeout_seconds <= 0:
            return
        if (time.monotonic() - started) > self._config.timeout_seconds:
            raise CodeScanTimeoutError(f"code scan exceeded {self._config.timeout_seconds}s budget")

    def _resolve_issued_products(
        self,
        *,
        context: ImageProcessingContext,
        consolidated,
        evidence: dict | None,
        duration_ms: int,
        mode: str,
    ) -> tuple[list[ProcessedProductLabel], dict | None, ImageProcessingResult | None]:
        """Map consolidator D1 hits through issued registry. Legacy PIPE leaves product_results empty."""
        if consolidated.rejections:
            evidence = {
                **(evidence or {}),
                "product_label_rejections": [
                    {
                        "validation_status": r.validation_status,
                        "raw_value_sha256": hashlib.sha256(
                            (r.raw_value or "").encode("utf-8")
                        ).hexdigest(),
                        "detection_index": r.detection_index,
                        "label_id": r.label_id,
                        "detail": r.detail,
                        "symbology": r.symbology,
                    }
                    for r in consolidated.rejections
                ],
            }

        if not consolidated.product_results:
            return [], evidence, None

        client_id = (context.client_id or "").strip()
        if not client_id:
            self._metrics.increment("product_label_client_context_missing_total")
            fail = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=mode,
                error_code="PRODUCT_LABEL_CLIENT_CONTEXT_MISSING",
                error_message="inventory client_id required to validate issued product labels",
                evidence=evidence,
                processing_duration_ms=duration_ms,
                warnings=["PRODUCT_LABEL_CLIENT_CONTEXT_MISSING"],
                product_results=[],
            )
            return [], evidence, fail
        if self._issued_label_resolver is None:
            self._metrics.increment("product_label_resolver_missing_total")
            fail = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=mode,
                error_code="PRODUCT_LABEL_RESOLVER_UNAVAILABLE",
                error_message="IssuedProductLabelResolver is required for D1 labels",
                evidence=evidence,
                processing_duration_ms=duration_ms,
                warnings=["PRODUCT_LABEL_RESOLVER_UNAVAILABLE"],
                product_results=[],
            )
            return [], evidence, fail

        products: list[ProcessedProductLabel] = []
        registry_rejections: list[dict[str, object]] = []
        for p in consolidated.product_results:
            parsed = parse_product_label_payload(p.raw_payload or "")
            resolved = self._issued_label_resolver.resolve_parsed(
                parsed=parsed,
                expected_client_id=client_id,
                selected_detection_index=p.selected_detection_index,
                duplicate_detection_count=p.duplicate_detection_count,
                symbology=p.symbology,
            )
            if (
                resolved.status is ProductLabelOutcomeStatus.VALID
                and resolved.product is not None
            ):
                products.append(resolved.product)
            else:
                self._metrics.increment(
                    f"product_label_reject_{resolved.status.value.lower()}_total"
                )
                registry_rejections.append(
                    {
                        "validation_status": resolved.status.value,
                        "label_id": p.label_id,
                        "detail": resolved.detail,
                        "detection_index": p.selected_detection_index,
                    }
                )
        if registry_rejections:
            evidence = {
                **(evidence or {}),
                "product_label_registry_rejections": registry_rejections,
            }
        return products, evidence, None

    def _scan_with_variants(
        self, asset: SourceAsset, content: bytes, started: float
    ) -> list[CodeScanDetectionCandidate]:
        """Scan base image and optional rotations; merge candidates across variants.

        Dedupes by ``(code_type, code_value)`` preserving first-seen order so a code only
        visible after rotation is not dropped when another code appeared at 0°.
        """
        self._check_timeout(started)
        merged: list[CodeScanDetectionCandidate] = []
        seen: set[tuple[str, str]] = set()

        def _absorb(batch: list[CodeScanDetectionCandidate]) -> None:
            for cand in batch:
                key = (
                    getattr(cand.code_type, "value", str(cand.code_type)),
                    (cand.code_value or "").strip(),
                )
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                merged.append(cand)

        _absorb(list(self._scanner.scan_asset(asset, content)))
        if not self._config.enable_rotations:
            return merged

        rotation_angles = [90, 180, 270][: max(0, self._config.max_variants - 1)]
        for angle in rotation_angles:
            self._check_timeout(started)
            # Stop early if we already have several distinct symbols (budget).
            if len(merged) >= int(self._config.max_candidates_per_asset):
                self._metrics.increment("code_scan.max_candidates_per_asset_reached")
                logger.info(
                    "code_scan.max_candidates_per_asset_reached limit=%s",
                    self._config.max_candidates_per_asset,
                )
                break
            rotated = self._rotated_variant_bytes(content, angle)
            if rotated is None:
                break
            self._metrics.increment("code_scan.rotation_variant")
            _absorb(list(self._scanner.scan_asset(asset, rotated)))
        return merged

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
            selected = next((d for d in detections if d.detection_index == selected_idx), None)
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
