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

Supplier CODE_SCAN custom rules (Phase 2) are applied via ``LabelValidationService`` when
the job snapshot selects SUPPLIER for ITEM/POSITION. Dinamic D1 / DINAMIC_POSITION keep
their existing parsers and fail-closed integrity. OCR profile rules remain INTERNAL_OCR-only.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
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
from src.application.services.image_processing.code_scan_label_classifier import (
    CodeScanClassificationResult,
    CodeScanLabelClassifier,
)
from src.application.services.image_processing.code_scan_session import (
    CodeScanSessionResult,
    CodeScanStopReason,
    CodeScanVariantObservation,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.application.services.image_processing.processing_event_publisher import (
    ProcessingEventPublisher,
)
from src.application.services.label_validation import (
    LabelValidationService,
    item_profile_source,
    position_profile_source,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.assets.entities import SourceAsset
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    NormalizedItemLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import (
    DETECTOR_NAME,
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.product_labels.format import parse_product_label_payload
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)
from src.infrastructure.code_scanning.image_decode import (
    UnreadableImageError,
    UnsupportedImageFormatError,
)
from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarUnavailableError

logger = logging.getLogger(__name__)

STRATEGY_KEY = "CODE_SCAN"
_SUPPLIER_POSITION_DETECTOR_VERSION = "supplier-position-label-1.0.0"

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
    """Raised when prepare + decode variants exceed the decode/variants budget.

    The budget is cooperative: CHECK → PREPARE → CHECK → DECODE → CHECK per variant.
    It does **not** preemptively interrupt a blocked native decoder call (e.g. pyzbar);
    after the call returns, the budget is re-checked before success / more variants.
    """

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics: dict[str, Any] = dict(diagnostics or {})


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
    # Wall-clock budget for image preparation + barcode decode variants AFTER source
    # bytes are loaded (CODE_SCAN_VARIANTS_BUDGET_SECONDS). Does not cover storage I/O.
    timeout_seconds: int = 15
    enable_rotations: bool = True
    enable_preprocessing: bool = False
    max_variants: int = 4
    max_technical_attempts: int = 2
    max_candidates_per_asset: int = 24


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


_LOGISTIC_SEMANTIC_TYPES = frozenset(
    {
        "SSCC",
        "LOGISTIC_UNIT",
        "PALLET",
        "BOX",
        "LPN",
        "CONTAINER",
    }
)


def _processed_from_normalized_item(
    label: NormalizedItemLabel,
    *,
    detection_index: int,
    semantic_type: str | None,
) -> ProcessedProductLabel:
    """Map validated ITEM → ProcessedProductLabel without inventing SKU for logistic units."""
    semantic = (semantic_type or "").strip().upper() or None
    is_logistic = semantic in _LOGISTIC_SEMANTIC_TYPES and not (label.sku or "").strip()
    logistic_id = (label.label_id or "").strip() or None if is_logistic else None
    return ProcessedProductLabel(
        label_id=label.label_id,
        internal_code=label.sku,
        quantity=label.quantity,
        format_version="SUPPLIER_LOGISTIC_UNIT" if is_logistic else "SUPPLIER",
        checksum=None,
        validation_status=ProductLabelOutcomeStatus.VALID,
        selected_detection_index=detection_index,
        duplicate_detection_count=1,
        symbology=label.symbology,
        raw_payload=label.raw_payload,
        normalized_payload=label.raw_payload,
        semantic_type=semantic,
        logistic_unit_id=logistic_id,
    )


def _evidence_list_len(evidence: dict[str, Any] | None, key: str) -> int:
    if not evidence:
        return 0
    value = evidence.get(key)
    return len(value) if isinstance(value, list) else 0


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
        label_validation_service: LabelValidationService | None = None,
        position_label_detection_repo=None,
        monotonic_fn: Callable[[], float] | None = None,
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
        self._label_validation = label_validation_service or LabelValidationService()
        self._classifier = CodeScanLabelClassifier(self._label_validation)
        self._position_detection_repo = position_label_detection_repo
        self._monotonic = monotonic_fn or time.monotonic

    def _publish_asset_event(
        self,
        context: ImageProcessingContext,
        event_type: str,
        *,
        message: str | None = None,
        error_code: str | None = None,
        metadata: dict | None = None,
        severity: str = "INFO",
        duration_ms: int | None = None,
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
                duration_ms=duration_ms,
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

    def _storage_fetch_event_metadata(self, *, source_load_ms: int) -> dict:
        """Merge reader diagnostics into event metadata (no extra storage I/O)."""
        diag = getattr(self._reader, "last_fetch_diagnostics", None)
        if not isinstance(diag, dict):
            return {"storage_fetch_ms": source_load_ms}
        out: dict = {}
        for key in (
            "storage_backend",
            "bucket",
            "object_key",
            "byte_length",
            "storage_fetch_ms",
            "attempt",
            "success",
            "retry_status",
            "slow",
            "download_ms",
            "metadata_lookup_ms",
            "total_storage_ms",
            "credentials_expired_at_start",
            "error_type",
        ):
            if key in diag and diag[key] is not None:
                out[key] = diag[key]
        out.setdefault("storage_fetch_ms", source_load_ms)
        return out

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
        asset_started_at = self._monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        budget_ms = int(float(self._config.timeout_seconds) * 1000)
        self._metrics.increment("code_scan.assets_processed")
        self._publish_asset_event(
            context,
            "code_scan.asset_started",
            message="CODE_SCAN asset processing started",
            metadata={"asset_id": context.asset_id},
        )

        self._publish_asset_event(
            context,
            "code_scan.source_load_started",
            message="source asset byte load started",
        )
        source_load_started_at = self._monotonic()
        try:
            content = self._reader.read_image_bytes(asset)
        except FileNotFoundError as exc:
            source_load_ms = max(0, int((self._monotonic() - source_load_started_at) * 1000))
            storage_meta = self._storage_fetch_event_metadata(source_load_ms=source_load_ms)
            self._publish_asset_event(
                context,
                "asset.source_load_failed",
                message="source asset byte load failed",
                error_code="SOURCE_ASSET_NOT_FOUND",
                severity="ERROR",
                metadata={
                    "source_load_ms": source_load_ms,
                    "error_type": type(exc).__name__,
                    **storage_meta,
                },
                duration_ms=source_load_ms,
            )
            result = self._technical(
                context, mode, "SOURCE_ASSET_NOT_FOUND", str(exc), asset_started_at
            )
            self._finalize_asset_event(context, result)
            return result
        except (OSError, ValueError) as exc:
            # ValueError: missing storage_key / empty object from content reader.
            source_load_ms = max(0, int((self._monotonic() - source_load_started_at) * 1000))
            storage_meta = self._storage_fetch_event_metadata(source_load_ms=source_load_ms)
            self._publish_asset_event(
                context,
                "asset.source_load_failed",
                message="source asset byte load failed",
                error_code="SOURCE_ASSET_READ_FAILED",
                severity="ERROR",
                metadata={
                    "source_load_ms": source_load_ms,
                    "error_type": type(exc).__name__,
                    **storage_meta,
                },
                duration_ms=source_load_ms,
            )
            result = self._technical(
                context, mode, "SOURCE_ASSET_READ_FAILED", str(exc), asset_started_at
            )
            self._finalize_asset_event(context, result)
            return result

        source_load_ms = max(0, int((self._monotonic() - source_load_started_at) * 1000))

        if not content:
            self._publish_asset_event(
                context,
                "asset.source_load_failed",
                message="source asset bytes empty",
                error_code="SOURCE_ASSET_EMPTY",
                severity="ERROR",
                metadata={
                    "source_load_ms": source_load_ms,
                    "error_type": "EmptyContent",
                },
                duration_ms=source_load_ms,
            )
            result = self._technical(
                context,
                mode,
                "SOURCE_ASSET_EMPTY",
                "empty source asset content",
                asset_started_at,
            )
            self._finalize_asset_event(context, result)
            return result

        storage_meta = self._storage_fetch_event_metadata(source_load_ms=source_load_ms)
        self._publish_asset_event(
            context,
            "asset.source_loaded",
            message="source asset bytes loaded",
            metadata={
                "byte_length": len(content),
                "source_load_ms": source_load_ms,
                "observability_generation": "phase-timed",
                "decode_budget_started_after_source_load": True,
                **storage_meta,
            },
            duration_ms=source_load_ms,
        )
        if storage_meta.get("slow"):
            self._publish_asset_event(
                context,
                "asset.storage_fetch_slow",
                message="storage fetch exceeded slow warning threshold",
                severity="WARNING",
                metadata={
                    "duration_ms": storage_meta.get("storage_fetch_ms", source_load_ms),
                    "byte_length": len(content),
                    "bucket": storage_meta.get("bucket"),
                    "storage_backend": storage_meta.get("storage_backend"),
                    "asset_id": context.asset_id,
                },
                duration_ms=source_load_ms,
            )

        # Decode/variants budget starts AFTER source bytes are available.
        decode_budget_started_at = self._monotonic()
        self._publish_asset_event(
            context,
            "code_scan.decode_started",
            message="CODE_SCAN prepare+decode budget started",
            metadata={
                "timeout_scope": "decode",
                "configured_budget_ms": budget_ms,
                "source_load_ms": source_load_ms,
                "decode_budget_started_after_source_load": True,
                "observability_generation": "phase-timed",
            },
        )

        try:
            scan_session = self._scan_with_variants(
                asset,
                content,
                decode_budget_started_at,
                context=context,
            )
        except CodeScanTimeoutError as exc:
            self._metrics.increment("code_scan.timeout")
            diagnostics = dict(exc.diagnostics)
            diagnostics.setdefault("timeout_phase", "decode")
            diagnostics.setdefault("configured_budget_ms", budget_ms)
            diagnostics["source_load_ms"] = source_load_ms
            diagnostics.setdefault(
                "elapsed_budget_ms",
                max(0, int((self._monotonic() - decode_budget_started_at) * 1000)),
            )
            diagnostics.setdefault("remaining_budget_ms", 0)
            self._publish_asset_event(
                context,
                "code_scan.decode_failed",
                message="CODE_SCAN timeout",
                error_code="CODE_SCAN_TIMEOUT",
                severity="ERROR",
                metadata=diagnostics,
            )
            result = self._technical(
                context,
                mode,
                "CODE_SCAN_TIMEOUT",
                str(exc),
                asset_started_at,
                evidence={
                    "timeout_phase": diagnostics.get("timeout_phase", "decode"),
                    "configured_budget_ms": diagnostics.get("configured_budget_ms", budget_ms),
                    "elapsed_budget_ms": diagnostics.get("elapsed_budget_ms"),
                    "remaining_budget_ms": diagnostics.get("remaining_budget_ms", 0),
                    "source_load_ms": source_load_ms,
                    "prepare_ms": diagnostics.get("prepare_ms"),
                    "decode_ms": diagnostics.get("decode_ms"),
                },
            )
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
            result = self._technical(
                context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), asset_started_at
            )
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
            result = self._technical(
                context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), asset_started_at
            )
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
            result = self._technical(
                context, mode, "CODE_SCAN_SCANNER_ERROR", str(exc), asset_started_at
            )
            self._finalize_asset_event(context, result)
            return result

        candidates = list(scan_session.candidates)
        symbol_count = len(candidates)
        self._metrics.increment("code_scan.raw_symbols_total", amount=symbol_count)
        if not scan_session.scan_complete:
            self._metrics.increment("code_scan.scan_incomplete_total")
        if scan_session.partial_timeout:
            self._metrics.increment("code_scan.timeout_partial_total")
        decode_elapsed_ms = max(
            0, int((self._monotonic() - decode_budget_started_at) * 1000)
        )
        self._publish_asset_event(
            context,
            "code_scan.decode_completed",
            message="barcode/QR decode completed",
            metadata={
                "symbol_count": symbol_count,
                "scan_complete": scan_session.scan_complete,
                "scan_stop_reason": scan_session.stop_reason.value,
                "variants_attempted": scan_session.variants_attempted,
                "source_load_ms": source_load_ms,
                "prepare_ms": scan_session.prepare_ms,
                "decode_ms": scan_session.decode_ms,
                "decode_elapsed_ms": decode_elapsed_ms,
                "configured_budget_ms": budget_ms,
            },
            error_code="NO_CODE_SYMBOL_FOUND" if symbol_count == 0 else None,
            duration_ms=decode_elapsed_ms,
        )
        if symbol_count > 0:
            self._publish_asset_event(
                context,
                "code_scan.symbols_detected",
                message="symbols detected",
                metadata={
                    "symbol_count": symbol_count,
                    "scan_complete": scan_session.scan_complete,
                    "scan_stop_reason": scan_session.stop_reason.value,
                },
            )
            for idx, cand in enumerate(candidates):
                raw_payload = (cand.code_value or "").strip()
                symbology = symbology_for_candidate(cand)
                self._publish_asset_event(
                    context,
                    "code_scan.payload_decoded",
                    message="payload decoded",
                    metadata={
                        "detection_index": idx,
                        "symbology": symbology,
                        "raw_payload_sha256": _sha256_hex(raw_payload),
                        "raw_payload_length": len(raw_payload),
                    },
                )

        validation_ctx = self._validation_context(context)
        item_source = item_profile_source(validation_ctx)
        position_source = position_profile_source(validation_ctx)
        use_unified = validation_ctx.resolved_profiles is not None
        self._publish_profile_resolved_events(
            context,
            validation_ctx=validation_ctx,
            item_source=item_source,
            position_source=position_source,
        )

        item_candidates = candidates
        position_meta: dict | None = None
        classification: CodeScanClassificationResult | None = None
        duration_ms = int((self._monotonic() - asset_started_at) * 1000)

        if use_unified:
            classification = self._classifier.classify(
                candidates, context=validation_ctx
            )
            self._metrics.increment(
                "code_scan_candidate_total", amount=len(candidates)
            )
            if classification.has_ambiguity:
                self._metrics.increment("code_scan_ambiguous_total")
                ambiguity_evidence: dict[str, Any] = {
                    "label_kind_ambiguity": True,
                    "ambiguous_indexes": list(classification.ambiguous_indexes),
                    "rejections": [
                        {
                            "detection_index": r.detection_index,
                            "error_code": r.error_code,
                            "raw_value_sha256": r.raw_payload_hash,
                        }
                        for r in classification.rejections
                    ],
                }
                result = ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    evidence=ambiguity_evidence,
                    warnings=["AMBIGUOUS_LABEL_KIND"],
                    error_code=LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value,
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                    processing_duration_ms=duration_ms,
                )
                self._finalize_asset_event(context, result)
                return result

            if position_source is LabelProfileSource.SUPPLIER:
                position_meta = self._materialize_supplier_positions(
                    context=context,
                    asset=asset,
                    classification=classification,
                    validation_ctx=validation_ctx,
                )
                claimed = set(classification.position_candidate_indexes) | {
                    r.detection_index
                    for r in classification.rejections
                    if r.error_code
                    and (
                        "DINAMIC" in r.error_code
                        or r.error_code
                        == LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value
                        or r.error_code == "DUPLICATE"
                    )
                }
                if item_source is LabelProfileSource.SUPPLIER:
                    item_candidates = list(classification.item_candidates)
                elif classification.items:
                    item_candidates = list(classification.item_candidates)
                else:
                    item_candidates = [
                        c
                        for idx, c in enumerate(candidates)
                        if idx not in claimed
                    ]
            elif self._position_detection is not None:
                # DINAMIC POSITION: existing HMAC/catalog path, but only on non-ITEM indexes.
                item_indexes = {i.detection_index for i in classification.items}
                position_pool = [
                    c
                    for idx, c in enumerate(candidates)
                    if idx not in item_indexes
                ]
                item_candidates, position_meta = self._run_dinamic_position_detection(
                    context=context,
                    asset=asset,
                    candidates=candidates,
                    position_pool=position_pool,
                    protected_item_indexes=item_indexes,
                )
                if item_source is LabelProfileSource.SUPPLIER:
                    item_candidates = list(classification.item_candidates)
            elif item_source is LabelProfileSource.SUPPLIER:
                item_candidates = list(classification.item_candidates)
        else:
            # Legacy jobs (no label_profiles): Dinamic position-first then consolidator.
            if self._position_detection is not None:
                item_candidates, position_meta = self._run_dinamic_position_detection(
                    context=context,
                    asset=asset,
                    candidates=candidates,
                    position_pool=candidates,
                    protected_item_indexes=set(),
                )

        detections = self._to_detection_inputs(item_candidates)
        evidence: dict[str, Any] | None = None

        if item_source is LabelProfileSource.SUPPLIER and use_unified:
            product_results, evidence, supplier_fail = self._resolve_supplier_products_from_classification(
                context=context,
                validation_ctx=validation_ctx,
                classification=classification,
                duration_ms=int((self._monotonic() - asset_started_at) * 1000),
            )
            if supplier_fail is not None:
                self._finalize_asset_event(context, supplier_fail)
                return supplier_fail
            consolidated = self._consolidator.consolidate([])
            duration_ms = int((self._monotonic() - asset_started_at) * 1000)
            evidence = evidence or self._build_evidence(
                consolidated, detections, scan_session=scan_session
            )
            if position_meta:
                evidence = {**(evidence or {}), "position_label_detection": position_meta}
            if classification is not None and classification.rejections:
                evidence = {
                    **(evidence or {}),
                    "supplier_label_rejections": [
                        {
                            "validation_status": r.error_code,
                            "detail": r.detail,
                            "detection_index": r.detection_index,
                            "raw_value_sha256": r.raw_payload_hash,
                        }
                        for r in classification.rejections
                        if r.label_kind is LabelKind.ITEM or r.label_kind is None
                    ],
                }
        elif item_source is LabelProfileSource.SUPPLIER:
            product_results, evidence, supplier_fail = self._resolve_supplier_products(
                context=context,
                validation_ctx=validation_ctx,
                item_candidates=item_candidates,
                scan_session=scan_session,
                position_meta=position_meta,
                duration_ms=int((self._monotonic() - asset_started_at) * 1000),
                mode=mode,
            )
            if supplier_fail is not None:
                self._finalize_asset_event(context, supplier_fail)
                return supplier_fail
            consolidated = self._consolidator.consolidate([])
            duration_ms = int((self._monotonic() - asset_started_at) * 1000)
            evidence = evidence or self._build_evidence(
                consolidated, detections, scan_session=scan_session
            )
            if position_meta:
                evidence = {**(evidence or {}), "position_label_detection": position_meta}
        else:
            supplier_configured = use_unified and (
                item_source is LabelProfileSource.SUPPLIER
                or position_source is LabelProfileSource.SUPPLIER
            )
            if supplier_configured:
                blocked = self._supplier_kind_aware_legacy_blocked_result(
                    context=context,
                    classification=classification,
                    mode=mode,
                    asset_started_at=asset_started_at,
                    scan_session=scan_session,
                    item_source=item_source,
                    position_source=position_source,
                )
                if blocked is not None:
                    self._finalize_asset_event(context, blocked)
                    return blocked
            consolidated = self._consolidator.consolidate(detections)

            duration_ms = int((self._monotonic() - asset_started_at) * 1000)
            evidence = self._build_evidence(consolidated, detections, scan_session=scan_session)
            if position_meta:
                evidence = {**(evidence or {}), "position_label_detection": position_meta}

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

        # Never apply OCR text-profile validation here. OCR profile rules are for
        # INTERNAL_OCR; AI fallback uses prompts.

        scan_warnings = self._scan_session_warnings(scan_session)
        if consolidated.product_results:
            self._metrics.increment(
                "code_scan.d1_candidates_total",
                amount=len(consolidated.product_results) + len(consolidated.rejections),
            )
            self._metrics.increment(
                "product_labels_rejected_total",
                amount=len(consolidated.rejections),
            )

        if consolidated.status in (
            CodeConsolidationStatus.RESOLVED,
            CodeConsolidationStatus.RESOLVED_MULTI,
        ) or (
            item_source is LabelProfileSource.SUPPLIER and product_results
        ):
            # D1 path: consolidator produced product_results that must pass registry.
            if consolidated.product_results and not product_results:
                consolidated = type(consolidated)(
                    status=CodeConsolidationStatus.NO_VALID_CODE,
                    warnings=(*consolidated.warnings, "NO_VALID_ISSUED_PRODUCT_LABEL"),
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
                    "code_scan.resolved job_id=%s asset_id=%s original_filename=%s "
                    "raw_symbols_count=%s product_count=%s product_label_ids=%s "
                    "rejected_label_ids=%s rejected_count=%s "
                    "scan_complete=%s scan_stop_reason=%s "
                    "position_candidates=%s duration_ms=%s",
                    context.job_id,
                    context.asset_id,
                    getattr(asset, "original_filename", None),
                    len(detections),
                    counted,
                    [p.label_id for p in product_results if getattr(p, "label_id", None)],
                    [
                        r.label_id
                        for r in consolidated.rejections
                        if getattr(r, "label_id", None)
                    ],
                    len(consolidated.rejections)
                    + _evidence_list_len(
                        evidence, "product_label_registry_rejections"
                    ),
                    scan_session.scan_complete,
                    scan_session.stop_reason.value,
                    (position_meta or {}).get("position_candidate_count"),
                    duration_ms,
                )
                first = product_results[0] if product_results else None
                primary_code = (
                    (
                        (getattr(first, "internal_code", None) or "").strip()
                        or (getattr(first, "label_id", None) or "").strip()
                        or (getattr(first, "logistic_unit_id", None) or "").strip()
                        or None
                    )
                    if first is not None
                    else consolidated.internal_code
                )
                primary_qty = (
                    product_results[0].quantity
                    if product_results
                    else consolidated.quantity
                )
                # Logistic units (SSCC/LPN) are recognized without inventing SKU/qty —
                # inventory ProductRecord auto-resolve still requires trade-item fields.
                # MINIMAL identity mode resolves without inventing enrichment.
                logistic_only = bool(product_results) and all(
                    getattr(p, "format_version", None) == "SUPPLIER_LOGISTIC_UNIT"
                    for p in product_results
                )
                item_cfg = (
                    validation_ctx.item_extraction_configuration
                    if validation_ctx is not None
                    else None
                )
                minimal = bool(
                    item_cfg is not None and getattr(item_cfg, "is_minimal", lambda: False)()
                )
                status = (
                    ImageResultStatus.PENDING_MANUAL_REVIEW
                    if logistic_only and not minimal
                    else ImageResultStatus.RESOLVED_INTERNAL
                )
                if logistic_only and not minimal:
                    evidence = {
                        **(evidence or {}),
                        "logistic_unit_review": True,
                        "limitation": (
                            "LOGISTIC_UNIT_NO_PRODUCT_RECORD: "
                            "SSCC/LPN recognized; inventory SKU rows not auto-created"
                        ),
                    }
                elif logistic_only and minimal:
                    evidence = {
                        **(evidence or {}),
                        "identity_valid": True,
                        "enrichment_complete": False,
                        "logistic_unit_identity_only": True,
                    }
                result = ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=status,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    internal_code=primary_code,
                    quantity=float(primary_qty) if primary_qty is not None else None,
                    evidence=evidence,
                    warnings=list(consolidated.warnings) + scan_warnings,
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
                        "status": status.value,
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
                supplier_position_only = (
                    position_meta.get("position_profile_source")
                    == LabelProfileSource.SUPPLIER.value
                    and position_ok
                )
                if supplier_position_only:
                    # SUPPLIER POSITION materialized; absence of ITEM is a successful position-only asset.
                    self._metrics.increment("code_scan.position_only")
                    position_evidence = {
                        **(evidence or {}),
                        "result_kind": "POSITION_ONLY",
                        "position_label_detection": position_meta,
                        "profile_validation_executed": True,
                    }
                    result = ImageProcessingResult(
                        job_id=context.job_id,
                        asset_id=context.asset_id,
                        status=ImageResultStatus.RESOLVED_INTERNAL,
                        processing_mode=mode,
                        resolved_by=STRATEGY_KEY,
                        evidence=position_evidence,
                        warnings=list(consolidated.warnings)
                        + scan_warnings
                        + ["POSITION_LABEL_ONLY"],
                        error_code=None,
                        execution_scope=ExecutionScope.SINGLE_ASSET,
                        logical_asset_attempt=False,
                        processing_duration_ms=duration_ms,
                    )
                    self._finalize_asset_event(context, result)
                    return result
                error_code = (
                    "POSITION_LABEL_UNRESOLVED"
                    if not position_ok
                    else None
                )
                self._metrics.increment("code_scan.position_only")
                result = ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=(
                        ImageResultStatus.RESOLVED_INTERNAL
                        if position_ok
                        else ImageResultStatus.UNRECOGNIZED
                    ),
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    evidence={
                        **(evidence or {}),
                        **({"result_kind": "POSITION_ONLY"} if position_ok else {}),
                        **({"position_label_detection": position_meta} if position_meta else {}),
                    },
                    warnings=(
                        list(consolidated.warnings) + scan_warnings + (["POSITION_LABEL_ONLY"] if position_ok else [])
                    ),
                    error_code=error_code,
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                    processing_duration_ms=duration_ms,
                )
                self._finalize_asset_event(context, result)
                return result

            supplier_expected = use_unified and symbol_count > 0
            if supplier_expected:
                blocked = self._supplier_kind_aware_legacy_blocked_result(
                    context=context,
                    classification=classification,
                    mode=mode,
                    asset_started_at=asset_started_at,
                    scan_session=scan_session,
                    item_source=item_source,
                    position_source=position_source,
                )
                if blocked is not None:
                    self._finalize_asset_event(context, blocked)
                    return blocked

            self._metrics.increment("code_scan.unrecognized")
            # Known Dinamic D1 symbols that failed checksum/registry must not become
            # NO_CODE_SYMBOL_FOUND → GLOBAL_EXTERNAL_FALLBACK invent-product.
            has_d1_rejection = bool(
                (evidence or {}).get("product_label_rejections")
                or (evidence or {}).get("product_label_registry_rejections")
                or any(
                    w in ("D1_CANDIDATES_FAILED", "NO_VALID_ISSUED_PRODUCT_LABEL")
                    for w in (consolidated.warnings or ())
                )
            )
            error_code = (
                "D1_CANDIDATES_FAILED" if has_d1_rejection else "NO_CODE_SYMBOL_FOUND"
            )
            result = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                evidence=evidence,
                warnings=list(consolidated.warnings) + scan_warnings,
                error_code=error_code,
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
            warnings=list(consolidated.warnings) + scan_warnings,
            error_code=consolidated.status.value,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
            processing_duration_ms=duration_ms,
        )
        self._finalize_asset_event(context, result)
        return result

    def _publish_profile_resolved_events(
        self,
        context: ImageProcessingContext,
        *,
        validation_ctx,
        item_source: LabelProfileSource,
        position_source: LabelProfileSource,
    ) -> None:
        resolved = validation_ctx.resolved_profiles
        if resolved is None:
            return
        for kind, profile, source in (
            (LabelKind.ITEM, resolved.item, item_source),
            (LabelKind.POSITION, resolved.position, position_source),
        ):
            config = (
                validation_ctx.item_extraction_configuration
                if kind is LabelKind.ITEM
                else validation_ctx.position_extraction_configuration
            )
            meta: dict[str, Any] = {
                "label_kind": kind.value,
                "source": source.value,
                "profile_id": profile.extraction_profile_id,
                "profile_version": profile.extraction_profile_version,
                "resolution_source": profile.resolution_source,
            }
            if config is not None:
                meta["recognition_mode"] = getattr(
                    getattr(config, "recognition_mode", None), "value", None
                )
                meta["semantic_type"] = getattr(config, "semantic_type", None)
            self._publish_asset_event(
                context,
                "code_scan.profile_resolved",
                message=f"{kind.value} profile resolved",
                metadata=meta,
            )

    def _supplier_kind_aware_legacy_blocked_result(
        self,
        *,
        context: ImageProcessingContext,
        classification,
        mode: str,
        asset_started_at: float,
        scan_session,
        item_source: LabelProfileSource,
        position_source: LabelProfileSource,
    ) -> ImageProcessingResult | None:
        """Block legacy consolidator only when SUPPLIER-kind evaluation failed with no DINAMIC escape."""
        if classification is None:
            return None
        if classification.items or classification.positions:
            return None
        if classification.leftover and (
            item_source is LabelProfileSource.DINAMIC
            or position_source is LabelProfileSource.DINAMIC
        ):
            return None

        supplier_rejections = [
            r
            for r in classification.rejections
            if (
                r.label_kind is LabelKind.ITEM
                and item_source is LabelProfileSource.SUPPLIER
            )
            or (
                r.label_kind is LabelKind.POSITION
                and position_source is LabelProfileSource.SUPPLIER
            )
            or (
                r.label_kind is None
                and (
                    item_source is LabelProfileSource.SUPPLIER
                    or position_source is LabelProfileSource.SUPPLIER
                )
            )
        ]
        if not supplier_rejections and not (
            classification.leftover
            and not (
                item_source is LabelProfileSource.DINAMIC
                or position_source is LabelProfileSource.DINAMIC
            )
        ):
            return None

        duration_ms = int((self._monotonic() - asset_started_at) * 1000)
        scan_warnings = self._scan_session_warnings(scan_session)
        if supplier_rejections:
            first = supplier_rejections[0]
            error_code = first.error_code or "SUPPLIER_LABEL_REJECTED"
            self._publish_asset_event(
                context,
                "code_scan.validation_completed",
                message="supplier validation rejected payload",
                metadata={
                    "label_kind": (
                        first.label_kind.value if first.label_kind else None
                    ),
                    "error_code": error_code,
                    "profile_validation_executed": True,
                },
            )
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                evidence={"profile_validation_executed": True},
                warnings=["SUPPLIER_LABEL_REJECTED"] + scan_warnings,
                error_code=error_code,
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
                processing_duration_ms=duration_ms,
            )
        if classification.leftover:
            self._publish_asset_event(
                context,
                "code_scan.validation_completed",
                message="supplier profile did not recognize payload",
                metadata={
                    "error_code": "SUPPLIER_PAYLOAD_NOT_RECOGNIZED",
                    "profile_validation_executed": True,
                },
            )
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                evidence={"profile_validation_executed": True},
                warnings=["SUPPLIER_PAYLOAD_NOT_RECOGNIZED"] + scan_warnings,
                error_code="SUPPLIER_PAYLOAD_NOT_RECOGNIZED",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
                processing_duration_ms=duration_ms,
            )
        return None

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

    def _check_timeout(
        self,
        decode_budget_started_at: float,
        *,
        prepare_ms: int | None = None,
        decode_ms: int | None = None,
    ) -> None:
        if self._config.timeout_seconds <= 0:
            return
        elapsed = self._monotonic() - decode_budget_started_at
        budget = float(self._config.timeout_seconds)
        if elapsed > budget:
            elapsed_ms = max(0, int(elapsed * 1000))
            configured_ms = int(budget * 1000)
            raise CodeScanTimeoutError(
                f"code scan decode exceeded {self._config.timeout_seconds}s budget",
                diagnostics={
                    "timeout_phase": "decode",
                    "configured_budget_ms": configured_ms,
                    "elapsed_budget_ms": elapsed_ms,
                    "remaining_budget_ms": 0,
                    "prepare_ms": prepare_ms,
                    "decode_ms": decode_ms,
                },
            )

    def _validation_context(self, context: ImageProcessingContext) -> LabelValidationContext:
        existing = context.label_validation_context
        if existing is not None:
            return existing
        # Legacy jobs / missing plumbing → Dinamic-default empty context.
        return LabelValidationContext(
            resolved_profiles=None,
            job_id=context.job_id,
            client_id=context.client_id,
        )

    def _run_dinamic_position_detection(
        self,
        *,
        context: ImageProcessingContext,
        asset: SourceAsset,
        candidates: list[CodeScanDetectionCandidate],
        position_pool: list[CodeScanDetectionCandidate],
        protected_item_indexes: set[int],
    ) -> tuple[list[CodeScanDetectionCandidate], dict | None]:
        """Existing Dinamic HMAC/catalog POSITION path (legacy + DINAMIC profile source)."""
        if self._position_detection is None:
            return candidates, None
        position_started = time.monotonic()
        try:
            from src.application.use_cases.position_label_detection.detect_image_position_labels import (
                ImagePositionDetectionCommand,
            )
            from src.domain.position_label_detection.entities import DetectedCode

            client_id = (context.client_id or "").strip()
            if not client_id:
                self._metrics.increment("position_label_detection_context_invalid_total")
                return candidates, {
                    "position_detection_count": 0,
                    "position_ambiguous": False,
                    "position_statuses": ["DETECTION_CONTEXT_INVALID"],
                    "position_detection_duration_ms": int(
                        (time.monotonic() - position_started) * 1000
                    ),
                }

            pool_ids = {id(c) for c in position_pool}
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
                if id(c) in pool_ids
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
            pos_indexes = set(pos_result.position_candidate_indexes)
            if pos_result.disabled or pos_result.context_invalid:
                item_candidates = list(candidates)
            else:
                item_candidates = [
                    c
                    for idx, c in enumerate(candidates)
                    if idx not in pos_indexes
                ]
            if protected_item_indexes:
                # Classifier already claimed ITEM indexes — keep them for ITEM path.
                item_by_idx = {idx: c for idx, c in enumerate(candidates)}
                merged = {
                    idx: item_by_idx[idx]
                    for idx in protected_item_indexes
                    if idx in item_by_idx
                }
                for idx, c in enumerate(candidates):
                    if idx not in pos_indexes and idx not in merged:
                        # leftover non-position
                        if idx not in protected_item_indexes:
                            pass
                item_candidates = [
                    c
                    for idx, c in enumerate(candidates)
                    if idx in protected_item_indexes or idx not in pos_indexes
                ]
            position_duration_ms = int((time.monotonic() - position_started) * 1000)
            position_meta = {
                "position_detection_count": len(pos_result.detections),
                "position_ambiguous": pos_result.ambiguous,
                "position_statuses": [
                    d.detection_status.value for d in pos_result.detections
                ],
                "position_detection_duration_ms": position_duration_ms,
                "position_candidate_indexes": list(pos_result.position_candidate_indexes),
                "position_profile_source": LabelProfileSource.DINAMIC.value,
            }
            self._metrics.increment("position_label_detection_total")
            self._metrics.increment(
                "position_label_detection_duration", amount=position_duration_ms
            )
            if any(d.detection_status.value == "VALID" for d in pos_result.detections):
                self._metrics.increment("position_label_detection_valid_total")
            if pos_result.ambiguous:
                self._metrics.increment("position_label_detection_ambiguous_total")
            return item_candidates, position_meta
        except Exception:
            self._metrics.increment("position_label_detection_failed_total")
            logger.exception(
                "position_label_detection_failed job_id=%s asset_id=%s",
                context.job_id,
                context.asset_id,
            )
            return candidates, None

    def _materialize_supplier_positions(
        self,
        *,
        context: ImageProcessingContext,
        asset: SourceAsset,
        classification: CodeScanClassificationResult,
        validation_ctx: LabelValidationContext,
    ) -> dict:
        """Persist SUPPLIER POSITION via the same detection table as Dinamic."""
        from datetime import datetime, timezone
        from uuid import uuid4

        positions = classification.positions
        statuses: list[str] = []
        indexes: list[int] = []
        rows: list[ImagePositionLabelDetection] = []
        now = datetime.now(timezone.utc)
        client_id = (context.client_id or "").strip() or "unknown"
        profile = (
            validation_ctx.resolved_profiles.position
            if validation_ctx.resolved_profiles
            else None
        )
        for classified in positions:
            label = classified.label
            cand = classified.candidate
            indexes.append(classified.detection_index)
            statuses.append(PositionLabelDetectionStatus.VALID.value)
            self._metrics.increment("code_scan_valid_total")
            rows.append(
                ImagePositionLabelDetection(
                    id=str(uuid4()),
                    client_id=client_id,
                    inventory_id=context.inventory_id,
                    job_id=context.job_id,
                    source_asset_id=context.asset_id,
                    client_image_id=getattr(asset, "upload_client_file_id", None),
                    ordered_capture_session_id=getattr(
                        asset, "ordered_capture_session_id", None
                    ),
                    sequence_number=getattr(asset, "sequence_number", None),
                    position_label_id=None,
                    public_identifier=label.position_id,
                    position_name_snapshot=label.position_id,
                    payload_version=None,
                    signature_status=PositionLabelSignatureStatus.SKIPPED,
                    detection_status=PositionLabelDetectionStatus.VALID,
                    confidence=cand.confidence,
                    bounding_box_json=cand.bounding_box_json,
                    rotation_degrees=_float_if_present(
                        cand.metadata_json.get("rotation_degrees")
                        if cand.metadata_json is not None
                        else None
                    ),
                    raw_payload_hash=_sha256_hex(label.raw_payload),
                    detector_name=DETECTOR_NAME,
                    detector_version=_SUPPLIER_POSITION_DETECTOR_VERSION,
                    created_at=now,
                    updated_at=now,
                    metadata_json={
                        "profile_source": LabelProfileSource.SUPPLIER.value,
                        "label_kind": LabelKind.POSITION.value,
                        "extraction_profile_id": (
                            profile.extraction_profile_id if profile else None
                        ),
                        "extraction_profile_version": (
                            profile.extraction_profile_version if profile else None
                        ),
                        "validation_outcome": LabelValidationStatus.VALID.value,
                        "pallet": label.pallet,
                        "side": label.side,
                        "level": label.level,
                    },
                )
            )

        for rejection in classification.rejections:
            if rejection.label_kind is LabelKind.POSITION or (
                rejection.error_code
                and (
                    "DINAMIC" in rejection.error_code
                    or rejection.error_code
                    == LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value
                )
            ):
                indexes.append(rejection.detection_index)
                statuses.append(rejection.error_code or "INVALID")

        if rows and self._position_detection_repo is not None:
            self._position_detection_repo.replace_asset_detections_atomically(
                job_id=context.job_id,
                source_asset_id=context.asset_id,
                detector_version=_SUPPLIER_POSITION_DETECTOR_VERSION,
                detections=rows,
            )
            self._metrics.increment(
                "position_label_detection_valid_total", amount=len(rows)
            )
        elif rows:
            logger.warning(
                "supplier_position_materialization_skipped_no_repo "
                "job_id=%s asset_id=%s count=%s",
                context.job_id,
                context.asset_id,
                len(rows),
            )

        return {
            "supplier_position_detection_count": len(positions),
            "position_detection_count": len(positions),
            "position_candidate_indexes": indexes,
            "position_statuses": statuses,
            "position_profile_source": LabelProfileSource.SUPPLIER.value,
            "position_ambiguous": False,
            "normalized_positions": [
                {
                    "position_id": p.label.position_id,
                    "pallet": p.label.pallet,
                    "side": p.label.side,
                    "level": p.label.level,
                    "detection_index": p.detection_index,
                }
                for p in positions
            ],
        }

    def _resolve_supplier_products_from_classification(
        self,
        *,
        context: ImageProcessingContext,
        validation_ctx: LabelValidationContext,
        classification: CodeScanClassificationResult | None,
        duration_ms: int,
    ) -> tuple[list[ProcessedProductLabel], dict[str, Any] | None, ImageProcessingResult | None]:
        if validation_ctx.item_extraction_configuration is None:
            self._metrics.increment("code_scan_invalid_total")
            fail = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=getattr(
                    context.identification_mode, "value", str(context.identification_mode)
                ),
                error_code="SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED",
                error_message=(
                    "SUPPLIER ITEM profile requires snapshotted extraction configuration"
                ),
                processing_duration_ms=duration_ms,
                warnings=["SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED"],
            )
            return [], None, fail
        products: list[ProcessedProductLabel] = []
        if classification is None:
            return (
                products,
                {"label_profile_source": LabelProfileSource.SUPPLIER.value},
                None,
            )
        for classified in classification.items:
            label = classified.label
            self._metrics.increment("code_scan_valid_total")
            semantic = None
            if validation_ctx.item_extraction_configuration is not None:
                semantic = validation_ctx.item_extraction_configuration.semantic_type
            products.append(
                _processed_from_normalized_item(
                    label,
                    detection_index=classified.detection_index,
                    semantic_type=semantic,
                )
            )
        profile = (
            validation_ctx.resolved_profiles.item
            if validation_ctx.resolved_profiles
            else None
        )
        evidence: dict[str, Any] = {
            "label_profile_source": LabelProfileSource.SUPPLIER.value,
            "label_kind": LabelKind.ITEM.value,
            "recognition_source": RecognitionSource.CODE_SCAN.value,
            "extraction_profile_id": profile.extraction_profile_id if profile else None,
            "extraction_profile_version": (
                profile.extraction_profile_version if profile else None
            ),
        }
        return products, evidence, None

    def _resolve_supplier_products(
        self,
        *,
        context: ImageProcessingContext,
        validation_ctx: LabelValidationContext,
        item_candidates: list[CodeScanDetectionCandidate],
        scan_session: CodeScanSessionResult,
        position_meta: dict | None,
        duration_ms: int,
        mode: str,
    ) -> tuple[list[ProcessedProductLabel], dict[str, Any] | None, ImageProcessingResult | None]:
        """Validate ITEM candidates with snapshot SUPPLIER rules (no Dinamic issued registry)."""
        del scan_session, position_meta, mode  # reserved for evidence extensions
        if validation_ctx.item_extraction_configuration is None:
            self._metrics.increment("code_scan_invalid_total")
            fail = ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=getattr(
                    context.identification_mode, "value", str(context.identification_mode)
                ),
                error_code="SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED",
                error_message=(
                    "SUPPLIER ITEM profile requires snapshotted extraction configuration"
                ),
                processing_duration_ms=duration_ms,
                warnings=["SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED"],
            )
            return [], None, fail

        products: list[ProcessedProductLabel] = []
        rejections: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for idx, cand in enumerate(item_candidates):
            raw = (cand.code_value or "").strip()
            self._metrics.increment("code_scan_candidate_total")
            result = self._label_validation.validate(
                CandidateLabel(
                    raw_payload=raw,
                    recognition_source=RecognitionSource.CODE_SCAN,
                    label_kind_hint=LabelKind.ITEM,
                    symbology=symbology_for_candidate(cand),
                ),
                context=validation_ctx,
                label_kind=LabelKind.ITEM,
            )
            if result.status is LabelValidationStatus.VALID and isinstance(
                result.label, NormalizedItemLabel
            ):
                self._metrics.increment("code_scan_valid_total")
                identity = ((result.label.label_id or result.label.sku) or "").strip()
                if identity in seen_ids:
                    rejections.append(
                        {
                            "validation_status": ProductLabelOutcomeStatus.DUPLICATE.value,
                            "label_id": identity,
                            "detection_index": idx,
                        }
                    )
                    continue
                seen_ids.add(identity)
                semantic = None
                if validation_ctx.item_extraction_configuration is not None:
                    semantic = validation_ctx.item_extraction_configuration.semantic_type
                products.append(
                    _processed_from_normalized_item(
                        result.label,
                        detection_index=idx,
                        semantic_type=semantic,
                    )
                )
            elif result.status is LabelValidationStatus.NOT_APPLICABLE:
                self._metrics.increment("code_scan_not_applicable_total")
            else:
                self._metrics.increment("code_scan_invalid_total")
                rejections.append(
                    {
                        "validation_status": result.error_code or result.status.value,
                        "detail": result.detail,
                        "detection_index": idx,
                        "raw_value_sha256": _sha256_hex(raw),
                    }
                )

        evidence: dict[str, Any] = {
            "label_profile_source": LabelProfileSource.SUPPLIER.value,
            "label_kind": LabelKind.ITEM.value,
            "recognition_source": RecognitionSource.CODE_SCAN.value,
        }
        if rejections:
            evidence["supplier_label_rejections"] = rejections
        return products, evidence, None

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
        self,
        asset: SourceAsset,
        content: bytes,
        decode_budget_started_at: float,
        *,
        context: ImageProcessingContext | None = None,
    ) -> CodeScanSessionResult:
        """Scan base image and optional rotations; merge candidates across variants.

        Dedupes by ``(code_type, code_value)`` preserving first-seen order so a code only
        visible after rotation is not dropped when another code appeared at 0°.

        ``decode_budget_started_at`` must be taken **after** source bytes are loaded.
        The budget covers image preparation + decoder variants (not storage I/O).

        Enforcement is cooperative per variant::

            CHECK → PREPARE → CHECK → DECODE → CHECK

        A blocked native decoder call is not preemptively interrupted; once it returns,
        the budget is re-checked before declaring the scan complete or starting more work.
        Timeout with candidates → ``scan_complete=False`` / ``TIMEOUT`` (partial), not a
        silent full success. Timeout with zero candidates still raises.
        """
        merged: list[CodeScanDetectionCandidate] = []
        seen: set[tuple[str, str]] = set()
        observations: list[CodeScanVariantObservation] = []
        variants_attempted = 0
        stop_reason = CodeScanStopReason.COMPLETE
        scan_complete = True
        prepare_ms = 0
        decode_ms = 0
        dims: dict[str, Any] = {
            "original_width": None,
            "original_height": None,
            "processed_width": None,
            "processed_height": None,
            "scale_ratio": None,
        }

        def _timeout_remaining_ms() -> int:
            budget = float(self._config.timeout_seconds)
            elapsed = self._monotonic() - decode_budget_started_at
            return max(0, int((budget - elapsed) * 1000))

        def _guard() -> None:
            self._check_timeout(
                decode_budget_started_at, prepare_ms=prepare_ms, decode_ms=decode_ms
            )

        def _absorb(batch: list[CodeScanDetectionCandidate]) -> int:
            added = 0
            for cand in batch:
                key = (
                    getattr(cand.code_type, "value", str(cand.code_type)),
                    (cand.code_value or "").strip(),
                )
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                merged.append(cand)
                added += 1
                self._log_symbol_safe(asset, cand)
            return added

        def _run_variant(angle: int, payload: bytes, variant_type: str) -> None:
            nonlocal variants_attempted, stop_reason, scan_complete, decode_ms
            if context is not None:
                self._publish_asset_event(
                    context,
                    "code_scan.decoder_variant_started",
                    message="barcode decoder variant started",
                    metadata={
                        "variant_type": variant_type,
                        "rotation_angle": angle,
                        "timeout_remaining_ms": _timeout_remaining_ms(),
                    },
                )
            variant_started = self._monotonic()
            batch: list[CodeScanDetectionCandidate] = []
            try:
                batch = list(self._scanner.scan_asset(asset, payload))
                self._metrics.increment("code_scan.variant_symbols_total", amount=len(batch))
                _absorb(batch)
                variants_attempted += 1
            finally:
                duration_ms = max(0, int((self._monotonic() - variant_started) * 1000))
                decode_ms += duration_ms
            obs = CodeScanVariantObservation(
                variant_type=variant_type,
                rotation_angle=angle,
                duration_ms=duration_ms,
                symbols_detected_count=len(batch),
                candidate_count_after_merge=len(merged),
                timeout_remaining_ms=_timeout_remaining_ms(),
                original_width=dims.get("original_width"),
                original_height=dims.get("original_height"),
                processed_width=dims.get("processed_width"),
                processed_height=dims.get("processed_height"),
                scale_ratio=dims.get("scale_ratio"),
            )
            observations.append(obs)
            logger.info(
                "code_scan.variant_result asset_id=%s original_filename=%s "
                "variant_type=%s angle=%s symbols=%s merged=%s duration_ms=%s "
                "timeout_remaining_ms=%s processed=%sx%s scale_ratio=%s",
                asset.id,
                getattr(asset, "original_filename", None),
                variant_type,
                angle,
                obs.symbols_detected_count,
                obs.candidate_count_after_merge,
                duration_ms,
                obs.timeout_remaining_ms,
                obs.processed_width,
                obs.processed_height,
                obs.scale_ratio,
            )

        def _session_kwargs(**extra: Any) -> dict[str, Any]:
            return {
                "candidates": tuple(merged),
                "variants_attempted": variants_attempted,
                "variant_observations": tuple(observations),
                "prepare_ms": prepare_ms,
                "decode_ms": decode_ms,
                **dims,
                **extra,
            }

        try:
            # CHECK → PREPARE (base) → CHECK → DECODE → CHECK
            _guard()
            if context is not None:
                self._publish_asset_event(
                    context,
                    "code_scan.prepare_started",
                    message="CODE_SCAN image preparation started",
                )
            prepare_started_at = self._monotonic()
            dims = self._image_dimensions(content)
            # Align 0° with configured max_image_side (rotations already downscaled).
            base_payload = self._prepared_scan_bytes(content, angle=0) or content
            prepare_ms = max(0, int((self._monotonic() - prepare_started_at) * 1000))
            if context is not None:
                self._publish_asset_event(
                    context,
                    "code_scan.prepare_completed",
                    message="CODE_SCAN image preparation completed",
                    metadata={"prepare_ms": prepare_ms},
                    duration_ms=prepare_ms,
                )
            _guard()
            _run_variant(0, base_payload, "base")
            _guard()

            if not self._config.enable_rotations:
                return CodeScanSessionResult(
                    scan_complete=True,
                    stop_reason=CodeScanStopReason.ROTATIONS_DISABLED,
                    **_session_kwargs(),
                )

            rotation_angles = [90, 180, 270][: max(0, self._config.max_variants - 1)]
            for angle in rotation_angles:
                # CHECK → PREPARE (rotation) → CHECK → DECODE → CHECK
                _guard()
                if len(merged) >= int(self._config.max_candidates_per_asset):
                    self._metrics.increment("code_scan.max_candidates_reached_total")
                    self._metrics.increment("code_scan.max_candidates_per_asset_reached")
                    stop_reason = CodeScanStopReason.MAX_CANDIDATES
                    scan_complete = False
                    logger.info(
                        "code_scan.max_candidates_per_asset_reached asset_id=%s limit=%s "
                        "merged=%s stop_reason=%s",
                        asset.id,
                        self._config.max_candidates_per_asset,
                        len(merged),
                        stop_reason.value,
                    )
                    break
                rot_prep_started = self._monotonic()
                rotated = self._prepared_scan_bytes(content, angle=angle)
                prepare_ms += max(0, int((self._monotonic() - rot_prep_started) * 1000))
                _guard()
                if rotated is None:
                    # One failed variant must not abort remaining angles.
                    logger.info(
                        "code_scan.variant_prepare_failed asset_id=%s angle=%s",
                        asset.id,
                        angle,
                    )
                    continue
                self._metrics.increment("code_scan.rotation_variant")
                _run_variant(angle, rotated, "rotation")
                _guard()
        except CodeScanTimeoutError:
            if merged:
                self._metrics.increment("code_scan.timeout_partial")
                stop_reason = CodeScanStopReason.TIMEOUT
                scan_complete = False
                logger.info(
                    "code_scan.timeout_partial asset_id=%s candidates=%s "
                    "variants_attempted=%s original_filename=%s",
                    asset.id,
                    len(merged),
                    variants_attempted,
                    getattr(asset, "original_filename", None),
                )
                return CodeScanSessionResult(
                    scan_complete=False,
                    stop_reason=CodeScanStopReason.TIMEOUT,
                    **_session_kwargs(),
                )
            raise

        return CodeScanSessionResult(
            scan_complete=scan_complete,
            stop_reason=stop_reason,
            **_session_kwargs(),
        )

    def _log_symbol_safe(self, asset: SourceAsset, cand: CodeScanDetectionCandidate) -> None:
        raw = (cand.code_value or "").strip()
        label_id = None
        classification = "OTHER"
        try:
            d1 = parse_product_label_payload(raw)
            if d1.status.value != "NOT_OUR_FORMAT":
                classification = "PRODUCT_D1"
                label_id = d1.label_id
            elif '"type":"DINAMIC_POSITION"' in raw.replace(" ", "") or (
                '"type": "DINAMIC_POSITION"' in raw
            ):
                classification = "POSITION"
            elif "|" in raw:
                classification = "LEGACY_PRODUCT"
        except Exception:
            classification = "OTHER"
        logger.info(
            "code_scan.symbol asset_id=%s symbology=%s classification=%s "
            "label_id=%s raw_value_hash=%s",
            asset.id,
            symbology_for_candidate(cand),
            classification,
            label_id,
            _sha256_hex(raw) if raw else None,
        )

    def _image_dimensions(self, content: bytes) -> dict[str, Any]:
        try:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(content)) as img:
                oriented = (ImageOps.exif_transpose(img) or img).convert("RGB")
                ow, oh = oriented.size
                processed_img = self._maybe_downscale(oriented)
                pw, ph = processed_img.size
            scale = (pw / float(ow)) if ow else None
            return {
                "original_width": int(ow),
                "original_height": int(oh),
                "processed_width": int(pw),
                "processed_height": int(ph),
                "scale_ratio": float(scale) if scale is not None else None,
            }
        except Exception:
            return {
                "original_width": None,
                "original_height": None,
                "processed_width": None,
                "processed_height": None,
                "scale_ratio": None,
            }

    def _prepared_scan_bytes(self, content: bytes, *, angle: int) -> bytes | None:
        """Oriented (+ optional downscale) PNG, optionally rotated. None if undecodable."""
        try:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(content)) as img:
                oriented = ImageOps.exif_transpose(img) or img
                oriented = oriented.convert("RGB")
                oriented = self._maybe_downscale(oriented)
                frame = oriented.rotate(-angle, expand=True) if angle else oriented
                buf = io.BytesIO()
                frame.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            return None

    def _rotated_variant_bytes(self, content: bytes, angle: int) -> bytes | None:
        """Best-effort rotated (and downscaled) PNG bytes; None if undecodable here."""
        return self._prepared_scan_bytes(content, angle=angle)

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

    def _scan_session_warnings(self, scan_session: CodeScanSessionResult) -> list[str]:
        if scan_session.partial_timeout:
            return ["CODE_SCAN_PARTIAL_TIMEOUT"]
        if (
            not scan_session.scan_complete
            and scan_session.stop_reason is CodeScanStopReason.MAX_CANDIDATES
        ):
            return ["CODE_SCAN_MAX_CANDIDATES"]
        return []

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

    def _build_evidence(
        self,
        consolidated,
        detections,
        *,
        scan_session: CodeScanSessionResult | None = None,
    ) -> dict | None:
        base: dict[str, Any] = {
            "scanner_name": self._scanner_name(),
            "scanner_version": self._scanner_version(),
            "detection_count": len(detections),
        }
        if scan_session is not None:
            base.update(
                {
                    "scan_complete": scan_session.scan_complete,
                    "scan_stop_reason": scan_session.stop_reason.value,
                    "variant_count": scan_session.variants_attempted,
                    "raw_symbols_count": len(scan_session.candidates),
                    "d1_candidate_count": len(consolidated.product_results)
                    + len(consolidated.rejections),
                    "valid_product_count": len(consolidated.product_results),
                    "rejected_product_count": len(consolidated.rejections),
                    "original_width": scan_session.original_width,
                    "original_height": scan_session.original_height,
                    "processed_width": scan_session.processed_width,
                    "processed_height": scan_session.processed_height,
                    "scale_ratio": scan_session.scale_ratio,
                }
            )
        if not detections:
            return base
        selected_idx = consolidated.selected_detection_index
        selected = None
        if selected_idx is not None:
            selected = next((d for d in detections if d.detection_index == selected_idx), None)
        if selected is None:
            selected = detections[0]
        base.update(
            {
                "symbology": selected.symbology,
                "raw_value_hash": _sha256_hex(selected.raw_value),
                "bounding_box": selected.bounding_box,
                "distinct_codes": len(consolidated.distinct_codes),
            }
        )
        return base

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
        asset_started_at: float,
        *,
        evidence: dict[str, Any] | None = None,
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
            evidence=evidence,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
            processing_duration_ms=int((self._monotonic() - asset_started_at) * 1000),
        )


__all__ = [
    "CodeScanConfig",
    "CodeScanMetrics",
    "CodeScanProcessingStrategy",
    "CodeScanSessionResult",
    "CodeScanStopReason",
    "CodeScanTimeoutError",
    "STRATEGY_KEY",
    "symbology_for_candidate",
]
