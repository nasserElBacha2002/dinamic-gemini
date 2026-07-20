"""Phase 4 — Internal OCR per-image processing strategy.

Loads one source asset, runs a bounded preprocessing + OCR variant loop, extracts fields,
normalizes/validates, and returns an :class:`ImageProcessingResult`.

Hard constraints (no LLM fallback, no multi-label per image):
- ONE image → at most ONE resolved position (SINGLE_ASSET scope).
- RESOLVED_INTERNAL only when valid internal_code + positive-integer quantity.
- Ambiguity → PENDING_MANUAL_REVIEW (never arbitrary pick).
- No usable text → UNRECOGNIZED.
- Engine unavailable / timeout / corrupt image → FAILED_TECHNICAL.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from src.application.ports.internal_label_reader import (
    InternalLabelReader,
    InternalOcrContext,
    InternalOcrEngineTimeoutError,
    InternalOcrEngineUnavailableError,
    InternalOcrReadResult,
    OcrEngineTransientError,
    OcrVariantReadError,
)
from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
)
from src.application.services.image_processing.field_candidate_set import (
    FieldCandidateSet,
    apply_profile_validation,
)
from src.application.services.image_processing.ocr_candidate_to_field_candidate_mapper import (
    OcrCandidateToFieldCandidateMapper,
    serialize_ocr_candidate_evidence,
)
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldExtraction,
    OcrFieldExtractor,
)
from src.application.services.image_processing.ocr_image_preprocessor import (
    OcrImagePreprocessor,
)
from src.application.services.image_processing.ocr_numeric_candidate_generator import (
    mask_value,
)
from src.application.services.image_processing.ocr_profile_context import (
    OcrProfileContext,
    resolve_ocr_profile_context,
)
from src.application.services.image_processing.ocr_result_normalizer import (
    NormalizedOcrLabel,
    OcrClientFieldRules,
    OcrNormalizeStatus,
    OcrResultNormalizer,
)
from src.application.services.legacy_processing_metrics import (
    record_processing_event_publish_failed,
)
from src.domain.assets.entities import SourceAsset
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)

logger = logging.getLogger(__name__)

STRATEGY_KEY = "INTERNAL_OCR"
PROCESSOR_NAME = "internal_ocr"
PROCESSOR_VERSION = "1.0.0"


class InternalOcrTimeoutError(RuntimeError):
    """Wall-clock budget exceeded between variants (honest mid-pipeline check)."""


@dataclass
class InternalOcrConfig:
    quantity_max: int
    max_image_dimension: int = 2048
    timeout_seconds: int = 20
    max_variants: int = 3
    language: str = "spa+eng"
    enable_gray_contrast: bool = True
    enable_adaptive_threshold: bool = True
    enable_deskew: bool = False
    client_rules: OcrClientFieldRules | None = None
    min_aggregate_confidence: float | None = None
    label_detection_enabled: bool = False
    diagnostic_evidence_enabled: bool = False
    page_segmentation_modes: tuple[int, ...] = (6, 11, 12)
    light_ocr_timeout_seconds: float = 3.0
    max_light_ocr_candidates: int = 3
    variant_plan_version: str = "v1"


@dataclass
class _VariantAttempt:
    """Per-variant OCR call outcome, kept small enough to embed in evidence (no tracebacks)."""

    variant_name: str
    executed: bool = True
    successful_engine_call: bool = False
    duration_ms: int | None = None
    error_code: str | None = None
    error_type: str | None = None

    def as_summary(self) -> dict[str, Any]:
        return {
            "variant_name": self.variant_name,
            "executed": self.executed,
            "successful_engine_call": self.successful_engine_call,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "error_type": self.error_type,
        }


class InternalOcrMetrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)


class SourceAssetContentReaderPort(Protocol):
    def read_image_bytes(self, asset: SourceAsset) -> bytes: ...


class InternalOcrProcessingStrategy:
    strategy_key = STRATEGY_KEY

    def __init__(
        self,
        *,
        reader: InternalLabelReader,
        content_reader: SourceAssetContentReaderPort,
        preprocessor: OcrImagePreprocessor,
        extractor: OcrFieldExtractor,
        normalizer: OcrResultNormalizer,
        config: InternalOcrConfig,
        metrics: InternalOcrMetrics | None = None,
        event_publisher: Any | None = None,
    ) -> None:
        self._reader = reader
        self._content_reader = content_reader
        self._preprocessor = preprocessor
        self._extractor = extractor
        self._normalizer = normalizer
        self._config = config
        self._metrics = metrics or InternalOcrMetrics()
        self._events = event_publisher

    @property
    def metrics(self) -> InternalOcrMetrics:
        return self._metrics

    @property
    def attempt_provider(self) -> str:
        return "internal_ocr"

    @property
    def attempt_model(self) -> str:
        # Must never raise: called before process() when creating ProcessingAttempt rows.
        try:
            version = getattr(self._reader, "engine_version", None) or "unknown"
        except Exception:
            version = "unknown"
        name = getattr(self._reader, "engine_name", None) or "ocr"
        return f"{name}/{version}"

    def process(self, context: ImageProcessingContext, asset: SourceAsset) -> ImageProcessingResult:
        """Orchestrate one asset. Expected failures return results; unexpected raise."""
        started = time.monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        try:
            result = self._process_core(context, asset)
        except (
            FileNotFoundError,
            InternalOcrTimeoutError,
            InternalOcrEngineTimeoutError,
            InternalOcrEngineUnavailableError,
            ExtractionProfileConfigurationError,
            OSError,
        ) as exc:
            # Typed / expected operational failures → functional technical result.
            error_code = self._expected_error_code(exc)
            result = self._technical(
                context,
                mode,
                error_code,
                f"{type(exc).__name__}: {exc}",
                started,
            )
            self._emit_asset_finalized(context, result)
            return result
        except Exception:
            # Programming defects / unexpected errors: log, emit, do NOT normalize away.
            logger.exception(
                "internal_ocr.strategy_unexpected job_id=%s asset_id=%s",
                context.job_id,
                context.asset_id,
            )
            self._emit(
                context,
                "asset.processing_failed",
                message="unexpected strategy exception",
                error_code="INTERNAL_OCR_STRATEGY_EXCEPTION",
                severity="ERROR",
                metadata={
                    "stage": "PROCESS",
                    "exception_type": "unexpected",
                },
            )
            failed = self._technical(
                context,
                mode,
                "INTERNAL_OCR_STRATEGY_EXCEPTION",
                "unexpected strategy exception",
                started,
            )
            self._emit_asset_finalized(context, failed)
            raise
        self._emit_asset_finalized(context, result)
        return result

    @staticmethod
    def _expected_error_code(exc: BaseException) -> str:
        if isinstance(exc, FileNotFoundError):
            return "SOURCE_ASSET_NOT_FOUND"
        if isinstance(exc, InternalOcrTimeoutError):
            return "INTERNAL_OCR_TIMEOUT"
        if isinstance(exc, InternalOcrEngineTimeoutError):
            return "INTERNAL_OCR_ENGINE_TIMEOUT"
        if isinstance(exc, InternalOcrEngineUnavailableError):
            return "INTERNAL_OCR_ENGINE_UNAVAILABLE"
        if isinstance(exc, ExtractionProfileConfigurationError):
            return "PROFILE_SNAPSHOT_INVALID"
        if isinstance(exc, OSError):
            return "SOURCE_ASSET_READ_FAILED"
        return "INTERNAL_OCR_EXPECTED_FAILURE"

    def _process_core(
        self, context: ImageProcessingContext, asset: SourceAsset
    ) -> ImageProcessingResult:
        started = time.monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        self._metrics.increment("ocr_images_total")

        try:
            content = self._content_reader.read_image_bytes(asset)
        except FileNotFoundError as exc:
            return self._technical(context, mode, "SOURCE_ASSET_NOT_FOUND", str(exc), started)
        except OSError as exc:
            return self._technical(context, mode, "SOURCE_ASSET_READ_FAILED", str(exc), started)

        if not content:
            return self._technical(
                context, mode, "SOURCE_ASSET_EMPTY", "empty source asset content", started
            )

        self._emit(
            context,
            "asset.source_loaded",
            message="source image bytes loaded",
            metadata={"byte_length": len(content)},
        )

        # Resolve profile once before any variant / extractor / validator work.
        profile_ctx = self._resolve_profile_context(context)
        if profile_ctx.is_invalid:
            return self._technical(
                context,
                mode,
                "PROFILE_SNAPSHOT_INVALID",
                profile_ctx.error_message or "invalid extraction profile snapshot",
                started,
            )
        profile_cfg = profile_ctx.configuration

        label_evidence: dict[str, Any] = {}
        ocr_source_bytes = content
        if self._config.label_detection_enabled:
            try:
                ocr_source_bytes, label_evidence, abort_code = self._detect_and_crop_label(
                    context, content, profile_cfg=profile_cfg
                )
            except ExtractionProfileConfigurationError as exc:
                return self._technical(
                    context,
                    mode,
                    "PROFILE_SNAPSHOT_INVALID",
                    str(exc.message if hasattr(exc, "message") else exc),
                    started,
                )
            if abort_code:
                duration_ms = int((time.monotonic() - started) * 1000)
                return ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=ImageResultStatus.UNRECOGNIZED,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    validation_errors=[abort_code],
                    warnings=[abort_code],
                    evidence=label_evidence
                    if self._config.diagnostic_evidence_enabled
                    else {
                        "selected_variant": None,
                        "error_code": abort_code,
                    },
                    provider_name=PROCESSOR_NAME,
                    model_name=self.attempt_model,
                    processing_duration_ms=duration_ms,
                    error_code=abort_code,
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                )

        try:
            prepared_list = self._preprocessor.prepare_variants(ocr_source_bytes)
        except ValueError as exc:
            return self._technical(context, mode, "OCR_IMAGE_DECODE_FAILED", str(exc), started)
        except (OSError, RuntimeError) as exc:
            return self._technical(context, mode, "OCR_PREPROCESS_FAILED", str(exc), started)

        variants = self._apply_variant_plan(prepared_list)

        best: tuple[NormalizedOcrLabel, InternalOcrReadResult, str, int] | None = None
        best_extraction: OcrFieldExtraction | None = None
        variants_attempted = 0
        variants_succeeded = 0
        variant_records: list[_VariantAttempt] = []
        preprocess_ms = int((time.monotonic() - started) * 1000)
        engine_ms_total = 0

        try:
            for prepared in variants:
                self._check_timeout(started)
                variants_attempted += 1
                self._metrics.increment("ocr_variants_attempted")
                variant_started = time.monotonic()
                psm = prepared.metadata.get("psm") if isinstance(prepared.metadata, dict) else None
                self._emit(
                    context,
                    "ocr.variant_started",
                    message=f"variant {prepared.variant_name}",
                    metadata={"variant": prepared.variant_name, "psm": psm},
                )
                ocr_ctx = InternalOcrContext(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    client_id=context.client_id,
                    language=self._config.language,
                    timeout_seconds=float(self._remaining_timeout(started)),
                    max_image_dimension=self._config.max_image_dimension,
                    page_segmentation_mode=int(psm) if psm is not None else 6,
                )
                try:
                    read = self._reader.read(prepared, ocr_ctx)
                except InternalOcrEngineTimeoutError as exc:
                    # Hard technical failure: bail out immediately (do not keep trying
                    # variants against a wall-clock budget that has already been blown).
                    return self._technical(context, mode, "INTERNAL_OCR_TIMEOUT", str(exc), started)
                except InternalOcrEngineUnavailableError as exc:
                    return self._technical(
                        context,
                        mode,
                        "INTERNAL_OCR_ENGINE_UNAVAILABLE",
                        str(exc),
                        started,
                    )
                except (OcrVariantReadError, OcrEngineTransientError) as exc:
                    # Soft-fail this variant only for known operational read errors.
                    variant_fail_ms = int((time.monotonic() - variant_started) * 1000)
                    variant_records.append(
                        _VariantAttempt(
                            variant_name=prepared.variant_name,
                            duration_ms=variant_fail_ms,
                            error_code="OCR_VARIANT_EXCEPTION",
                            error_type=type(exc).__name__,
                        )
                    )
                    self._emit(
                        context,
                        "ocr.variant_failed",
                        message=f"variant {prepared.variant_name} failed",
                        error_code="OCR_VARIANT_EXCEPTION",
                        duration_ms=variant_fail_ms,
                        severity="WARN",
                        metadata={
                            "variant": prepared.variant_name,
                            "psm": psm,
                            "successful_engine_call": False,
                            "error_type": type(exc).__name__,
                            "text_block_count": 0,
                            "candidate_count": 0,
                        },
                    )
                    logger.warning(
                        "internal_ocr.variant_failed job_id=%s asset_id=%s variant=%s err=%s",
                        context.job_id,
                        context.asset_id,
                        prepared.variant_name,
                        exc,
                    )
                    continue
                # Programming / contract / mapper / extractor defects: do not soft-fail.
                variants_succeeded += 1
                variant_duration_ms = int(read.duration_ms or 0)
                variant_records.append(
                    _VariantAttempt(
                        variant_name=prepared.variant_name,
                        successful_engine_call=True,
                        duration_ms=variant_duration_ms,
                    )
                )
                engine_ms_total += variant_duration_ms
                extraction = self._extractor.extract(read, configuration=profile_cfg)
                normalized = self._normalizer.normalize(extraction)
                stats = dict(extraction.stats or {})
                self._emit(
                    context,
                    "ocr.tokens_normalized",
                    message="ocr tokens normalized",
                    metadata={
                        "text_block_count": stats.get("raw_text_block_count", 0),
                        "normalized_token_count": stats.get("normalized_token_count", 0),
                        "numeric_token_count": stats.get("raw_numeric_token_count", 0),
                    },
                )
                self._emit(
                    context,
                    "ocr.anchors_detected",
                    message="ocr anchors detected",
                    metadata={
                        "configured_anchor_count": stats.get("configured_anchor_count", 0),
                        "exact_match_count": stats.get("exact_match_count", 0),
                        "fuzzy_match_count": stats.get("fuzzy_match_count", 0),
                        "matched_anchor_count": stats.get("matched_anchor_count", 0),
                    },
                )
                self._emit(
                    context,
                    "ocr.candidates_extracted",
                    message="ocr candidates extracted",
                    metadata={
                        "code_before_filter": stats.get("code_candidates_before_filter", 0),
                        "code_after_filter": stats.get("code_candidates_after_filter", 0),
                        "quantity_before_filter": stats.get("quantity_candidates_before_filter", 0),
                        "quantity_after_filter": stats.get("quantity_candidates_after_filter", 0),
                        "rejected_candidate_count": stats.get("rejected_candidate_count", 0),
                        "rejection_reasons": serialize_ocr_candidate_evidence(
                            stats.get("rejection_reasons") or {}
                        ),
                    },
                )
                self._emit_candidate_rejections(context, extraction.rejected_candidates)
                self._emit(
                    context,
                    "ocr.variant_completed",
                    message=f"variant {prepared.variant_name} completed",
                    duration_ms=variant_duration_ms,
                    metadata={
                        "variant": prepared.variant_name,
                        "psm": psm,
                        "successful_engine_call": True,
                        "text_block_count": len(getattr(read, "text_blocks", ()) or ()),
                        "candidate_count": (
                            len(extraction.internal_code_candidates)
                            + len(extraction.ean_candidates)
                            + len(extraction.quantity_candidates)
                        ),
                        "raw_numeric_token_count": stats.get("raw_numeric_token_count", 0),
                        "code_candidates_after_filter": stats.get(
                            "code_candidates_after_filter", 0
                        ),
                        "quantity_candidates_after_filter": stats.get(
                            "quantity_candidates_after_filter", 0
                        ),
                        "rejected_candidate_count": stats.get("rejected_candidate_count", 0),
                    },
                )

                candidate = normalized
                if normalized.status is OcrNormalizeStatus.RESOLVED:
                    if self._confidence_ok(read):
                        best = (normalized, read, prepared.variant_name, variants_attempted)
                        best_extraction = extraction
                        break
                    # Confidence gate failed: never accept this as the resolved answer.
                    # Build a fresh PENDING_MANUAL_REVIEW candidate instead of mutating
                    # `normalized` in place, so the rejected RESOLVED label is never the one
                    # that ends up driving the final (accepted) result below.
                    candidate = self._demote_low_confidence(normalized)
                    self._metrics.increment("ocr_low_confidence_total")

                if best is None or self._rank(candidate) < self._rank(best[0]):
                    best = (candidate, read, prepared.variant_name, variants_attempted)
                    best_extraction = extraction
        except InternalOcrTimeoutError as exc:
            return self._technical(context, mode, "INTERNAL_OCR_TIMEOUT", str(exc), started)

        duration_ms = int((time.monotonic() - started) * 1000)
        variant_failures = [r.as_summary() for r in variant_records if not r.successful_engine_call]

        if best is None:
            # No variant ever produced a successful engine call — this is a technical
            # failure of the OCR pass, not "no usable text" (that is UNRECOGNIZED, reached
            # via `normalized.status` below only when at least one call succeeded).
            return self._technical(
                context,
                mode,
                "INTERNAL_OCR_NO_VARIANT_RESULT",
                "all OCR variants failed",
                started,
                evidence={
                    "processor_name": PROCESSOR_NAME,
                    "processor_version": PROCESSOR_VERSION,
                    "variants_attempted": variants_attempted,
                    "variants_succeeded": variants_succeeded,
                    "variant_failures": variant_failures,
                    "selected_variant": None,
                },
            )

        normalized, read, variant_name, attempted = best
        evidence = self._build_evidence(
            normalized=normalized,
            read=read,
            variant_name=variant_name,
            variants_attempted=attempted,
            variants_succeeded=variants_succeeded,
            variant_failures=variant_failures,
            preprocess_ms=preprocess_ms,
            engine_ms=engine_ms_total,
        )
        if label_evidence:
            evidence = {**evidence, **label_evidence}

        if context.profile_aware_validation_enabled:
            # Prefer the extraction already computed for the selected OCR variant.
            extraction_for_profile = best_extraction or self._extractor.extract(
                read, configuration=profile_cfg
            )
            if self._config.diagnostic_evidence_enabled:
                evidence = {
                    **(evidence or {}),
                    "extraction_stats": serialize_ocr_candidate_evidence(
                        dict(extraction_for_profile.stats or {})
                    ),
                    "matched_anchors": serialize_ocr_candidate_evidence(
                        list(extraction_for_profile.matched_anchors or [])[:20]
                    ),
                    "rejected_candidates": serialize_ocr_candidate_evidence(
                        list(extraction_for_profile.rejected_candidates or [])[:30]
                    ),
                    "rejection_reasons": serialize_ocr_candidate_evidence(
                        (extraction_for_profile.stats or {}).get("rejection_reasons") or {}
                    ),
                    "numeric_tokens": serialize_ocr_candidate_evidence(
                        [
                            {
                                "masked_value": mask_value(c.value),
                                "length": len(c.value),
                                "confidence": c.confidence,
                                "extraction_method": c.extraction_method,
                                "anchor_text": c.anchor_text,
                            }
                            for c in extraction_for_profile.internal_code_candidates[:20]
                        ]
                    ),
                }
            if context.reference_template_annotations_enabled:
                from src.application.services.image_processing.reference_template_hint_resolver import (
                    ReferenceTemplateHintResolver,
                )

                hint_res = ReferenceTemplateHintResolver().resolve(
                    template_image_id=None,
                    profile_id=(
                        (context.supplier_extraction_profile or {}).get("supplier_profile_id")
                        if isinstance(context.supplier_extraction_profile, dict)
                        else None
                    ),
                    annotations=(),
                )
                evidence = {**(evidence or {}), **hint_res.evidence}
            return self._result_via_profile(
                context=context,
                mode=mode,
                extraction=extraction_for_profile,
                evidence=evidence or {},
                duration_ms=duration_ms,
                profile_cfg=profile_cfg,
            )

        if normalized.status is OcrNormalizeStatus.RESOLVED:
            self._metrics.increment("ocr_resolved_total")
            logger.info(
                "internal_ocr.resolved job_id=%s asset_id=%s variant=%s duration_ms=%s",
                context.job_id,
                context.asset_id,
                variant_name,
                duration_ms,
            )
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.RESOLVED_INTERNAL,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                internal_code=normalized.internal_code,
                quantity=float(normalized.quantity) if normalized.quantity is not None else None,
                additional_fields=dict(normalized.additional_fields),
                normalized_result={
                    "internal_code": normalized.internal_code,
                    "quantity": normalized.quantity,
                    "additional_fields": normalized.additional_fields,
                },
                warnings=list(normalized.warnings),
                evidence=evidence,
                provider_name=PROCESSOR_NAME,
                model_name=self.attempt_model,
                processing_duration_ms=duration_ms,
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        if normalized.status is OcrNormalizeStatus.UNRECOGNIZED:
            self._metrics.increment("ocr_unrecognized_total")
            if "NO_INTERNAL_CODE" in normalized.validation_errors:
                self._metrics.increment("ocr_missing_code_total")
            if (
                "QUANTITY_MISSING" in normalized.validation_errors
                or "MISSING_QUANTITY" in normalized.validation_errors
            ):
                self._metrics.increment("ocr_missing_quantity_total")
            # Code present + missing qty must go to manual review, not UNRECOGNIZED.
            if (
                normalized.internal_code
                and (
                    "QUANTITY_MISSING" in normalized.validation_errors
                    or "MISSING_QUANTITY" in normalized.validation_errors
                )
                and "NO_INTERNAL_CODE" not in normalized.validation_errors
                and "MISSING_INTERNAL_CODE" not in normalized.validation_errors
            ):
                self._metrics.increment("ocr_manual_review_total")
                return ImageProcessingResult(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                    processing_mode=mode,
                    resolved_by=STRATEGY_KEY,
                    internal_code=normalized.internal_code,
                    quantity=None,
                    additional_fields=dict(normalized.additional_fields),
                    validation_errors=["MISSING_QUANTITY"],
                    warnings=list(normalized.warnings),
                    evidence=evidence,
                    provider_name=PROCESSOR_NAME,
                    model_name=self.attempt_model,
                    processing_duration_ms=duration_ms,
                    error_code="MISSING_QUANTITY",
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                )
            return ImageProcessingResult(
                job_id=context.job_id,
                asset_id=context.asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                additional_fields=dict(normalized.additional_fields),
                validation_errors=list(normalized.validation_errors),
                warnings=list(normalized.warnings),
                evidence=evidence,
                provider_name=PROCESSOR_NAME,
                model_name=self.attempt_model,
                processing_duration_ms=duration_ms,
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        # AMBIGUOUS / PENDING_MANUAL_REVIEW
        if "AMBIGUOUS_INTERNAL_CODE" in normalized.warnings:
            self._metrics.increment("ocr_ambiguous_code_total")
        if "AMBIGUOUS_QUANTITY" in normalized.warnings:
            self._metrics.increment("ocr_ambiguous_quantity_total")
        self._metrics.increment("ocr_manual_review_total")
        self._metrics.increment("ocr_validation_failure_total")
        # LOW_OCR_CONFIDENCE takes precedence over the generic status code so callers/audits
        # can distinguish "confidence gate failed" from ordinary missing-field manual review.
        error_code = (
            "LOW_OCR_CONFIDENCE"
            if "LOW_OCR_CONFIDENCE" in normalized.validation_errors
            else normalized.status.value
        )
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=mode,
            resolved_by=STRATEGY_KEY,
            internal_code=normalized.internal_code,
            quantity=float(normalized.quantity) if normalized.quantity is not None else None,
            additional_fields=dict(normalized.additional_fields),
            validation_errors=list(normalized.validation_errors),
            warnings=list(normalized.warnings),
            evidence=evidence,
            provider_name=PROCESSOR_NAME,
            model_name=self.attempt_model,
            processing_duration_ms=duration_ms,
            error_code=error_code,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    def _resolve_profile_context(self, context: ImageProcessingContext) -> OcrProfileContext:
        return resolve_ocr_profile_context(
            context.supplier_extraction_profile
            if isinstance(context.supplier_extraction_profile, dict)
            else None
        )

    def _emit_candidate_rejections(
        self,
        context: ImageProcessingContext,
        rejected: list[dict[str, Any]] | None,
        *,
        sample_limit: int = 5,
    ) -> None:
        """Emit one aggregated rejection summary (+ optional sample), never unbounded events."""
        items = list(rejected or [])
        if not items:
            return
        reasons: Counter[str] = Counter()
        for rej in items:
            code = str(rej.get("reason_code") or "UNKNOWN")
            reasons[code] += 1
        sample = [
            {
                "field": rej.get("field"),
                "masked_value": rej.get("masked_value"),
                "length": rej.get("length"),
                "reason_code": rej.get("reason_code"),
                "source": rej.get("source"),
            }
            for rej in items[: max(0, int(sample_limit))]
        ]
        self._emit(
            context,
            "ocr.candidate_rejected",
            message="candidates rejected (aggregated)",
            severity="WARN",
            metadata={
                "rejected_total": len(items),
                "rejection_reasons": dict(reasons),
                "sample": sample,
                "sample_limit": sample_limit,
            },
        )

    def _emit(
        self,
        context: ImageProcessingContext,
        event_type: str,
        *,
        message: str | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
        severity: str = "INFO",
    ) -> None:
        """Best-effort telemetry — publish failures must not fail OCR processing."""
        if self._events is None:
            return
        try:
            self._events.publish(
                job_id=context.job_id,
                event_type=event_type,
                asset_id=context.asset_id,
                attempt_id=getattr(context, "attempt_id", None),
                strategy=STRATEGY_KEY,
                severity=severity,
                message=message,
                error_code=error_code,
                duration_ms=duration_ms,
                correlation_id=getattr(context, "correlation_id", None),
                metadata=metadata,
            )
        except Exception as exc:
            record_processing_event_publish_failed(
                event_type=event_type,
                err_type=type(exc).__name__,
            )
            self._metrics.increment("ocr_observability_publish_failed_total")
            flags = getattr(context, "__dict__", None)
            if isinstance(flags, dict):
                flags["_ocr_observability_incomplete"] = True
            logger.warning(
                "internal_ocr.event_publish_failed event_type=%s err=%s",
                event_type,
                type(exc).__name__,
            )

    def _detect_and_crop_label(
        self,
        context: ImageProcessingContext,
        content: bytes,
        *,
        profile_cfg: ExtractionProfileConfiguration,
    ) -> tuple[bytes, dict[str, Any], str | None]:
        from src.application.services.image_processing.label_geometry_normalizer import (
            LabelGeometryNormalizer,
        )
        from src.application.services.image_processing.label_region_detector import (
            LabelRegionDetector,
        )

        rules = profile_cfg.label_detection_rules

        self._emit(context, "label_detection.started", message="label detection started")
        detector = LabelRegionDetector(
            rules=rules,
            light_ocr_reader=self._reader,
            light_ocr_language=self._config.language,
            light_ocr_timeout_seconds=float(
                getattr(self._config, "light_ocr_timeout_seconds", 3.0)
            ),
            max_light_ocr_candidates=int(getattr(self._config, "max_light_ocr_candidates", 3)),
        )
        detection = detector.detect(content)
        selected = detection.selected_candidate
        self._emit(
            context,
            "label_detection.completed",
            message="label detection completed",
            duration_ms=detection.duration_ms,
            metadata={
                "candidate_count": len(detection.candidates),
                "selected": bool(selected),
                "selected_relative_area": (
                    selected.relative_area if selected is not None else None
                ),
                "matched_anchors": (list(selected.matched_anchors) if selected is not None else []),
                "failure_reason": detection.failure_reason,
                "light_ocr_executed": detection.light_ocr_executed,
                "light_ocr_failed": detection.light_ocr_failed,
                "anchor_requirement_met": detection.anchor_requirement_met,
                "anchor_match_policy": detection.anchor_match_policy,
            },
        )
        evidence: dict[str, Any] = {
            "label_detection": {
                "detected": detection.detected,
                "candidate_count": len(detection.candidates),
                "failure_reason": detection.failure_reason,
                "duration_ms": detection.duration_ms,
                "used_full_image_fallback": detection.used_full_image_fallback,
                "light_ocr_executed": detection.light_ocr_executed,
                "light_ocr_failed": detection.light_ocr_failed,
                "anchor_requirement_met": detection.anchor_requirement_met,
                "anchor_match_policy": detection.anchor_match_policy,
                "selected_relative_area": (
                    selected.relative_area if selected is not None else None
                ),
                "matched_anchors": (list(selected.matched_anchors) if selected is not None else []),
                "selected_polygon": (
                    [list(p) for p in selected.polygon] if selected is not None else None
                ),
            }
        }

        if not detection.detected and not rules.allow_full_image_fallback:
            return content, evidence, "LABEL_NOT_DETECTED"

        if selected is not None:
            self._emit(context, "label_region.selected", message="label region selected")

        normalizer = LabelGeometryNormalizer(
            allow_perspective_correction=bool(
                getattr(rules, "allow_deskew", rules.allow_perspective_correction)
            ),
        )
        try:
            geom = normalizer.normalize_region(
                content,
                selected,
                allow_full_image_fallback=rules.allow_full_image_fallback,
            )
        except ValueError as exc:
            if not rules.allow_full_image_fallback:
                evidence["label_geometry"] = {"failure_reason": str(exc)}
                return content, evidence, "LABEL_NOT_DETECTED"
            evidence["label_geometry"] = {"failure_reason": str(exc)}
            return content, evidence, None

        self._emit(
            context,
            "label_geometry.normalized",
            message="label geometry normalized",
            metadata={
                "deskew_applied": bool(geom.perspective_corrected),
                "perspective_transform_applied": False,
                "applied_rotation_deg": geom.applied_rotation_deg,
                "used_original_region": geom.used_original_region,
            },
        )
        evidence["label_geometry"] = {
            "exif_rotated": True,
            "deskew_applied": bool(geom.perspective_corrected),
            "perspective_transform_applied": False,
            "applied_rotation_deg": geom.applied_rotation_deg,
            "used_original_region": geom.used_original_region,
            "failure_reason": geom.failure_reason,
            "width": geom.width,
            "height": geom.height,
        }
        return geom.image_bytes, evidence, None

    def _apply_variant_plan(self, prepared_variants: list[Any]) -> list[Any]:
        """Map preprocess outputs through the versioned variant plan."""
        from src.application.ports.internal_label_reader import PreparedImage
        from src.application.services.image_processing.ocr_variant_plan import (
            VARIANT_PLAN_VERSION,
            build_ocr_variant_plan,
        )

        by_name = {p.variant_name: p for p in prepared_variants}
        # Alias without psm suffix from preprocessor.
        plan = build_ocr_variant_plan(
            max_total_engine_calls=int(self._config.max_variants),
            enable_gray_contrast=self._config.enable_gray_contrast,
            enable_adaptive_threshold=self._config.enable_adaptive_threshold,
            enable_deskew=self._config.enable_deskew,
            page_segmentation_modes=self._config.page_segmentation_modes or (6, 11, 12),
        )
        out: list[PreparedImage] = []
        for spec in plan:
            base = by_name.get(spec.preprocess_variant)
            if base is None:
                # Fall back to original if requested preprocess missing.
                base = by_name.get("original") or (
                    prepared_variants[0] if prepared_variants else None
                )
            if base is None:
                continue
            meta = dict(base.metadata or {})
            meta["psm"] = int(spec.psm)
            meta["variant_plan_version"] = VARIANT_PLAN_VERSION
            out.append(
                PreparedImage(
                    content=base.content,
                    width=base.width,
                    height=base.height,
                    variant_name=spec.name,
                    mime_type=base.mime_type,
                    metadata=meta,
                )
            )
        return out or list(prepared_variants)

    def _expand_psm_variants(self, variants: list[Any]) -> list[Any]:
        # Backward-compatible alias — prefer _apply_variant_plan.
        return self._apply_variant_plan(variants)

    def _rank(self, label: NormalizedOcrLabel) -> int:
        order = {
            OcrNormalizeStatus.RESOLVED: 0,
            OcrNormalizeStatus.PENDING_MANUAL_REVIEW: 1,
            OcrNormalizeStatus.AMBIGUOUS: 2,
            OcrNormalizeStatus.UNRECOGNIZED: 3,
        }
        return order.get(label.status, 9)

    def _confidence_ok(self, read: InternalOcrReadResult) -> bool:
        min_c = self._config.min_aggregate_confidence
        if min_c is None:
            # No threshold configured — confidence gating is disabled.
            return True
        if read.confidence is None:
            # A threshold IS configured but the engine reported no confidence value at all.
            # Treat that as insufficient evidence rather than silently accepting (fail
            # closed, not open, for auditability).
            return False
        return float(read.confidence) >= float(min_c)

    def _demote_low_confidence(self, normalized: NormalizedOcrLabel) -> NormalizedOcrLabel:
        """Reject a RESOLVED label that failed the confidence gate without mutating it.

        Returns a brand-new PENDING_MANUAL_REVIEW label so the original resolved candidate
        is never the object that ends up accepted as RESOLVED_INTERNAL further down.
        """
        return NormalizedOcrLabel(
            status=OcrNormalizeStatus.PENDING_MANUAL_REVIEW,
            internal_code=normalized.internal_code,
            quantity=normalized.quantity,
            additional_fields=dict(normalized.additional_fields),
            warnings=[*normalized.warnings, "LOW_OCR_CONFIDENCE"],
            validation_errors=[*normalized.validation_errors, "LOW_OCR_CONFIDENCE"],
            selected_code_rule=normalized.selected_code_rule,
            selected_qty_rule=normalized.selected_qty_rule,
        )

    def _check_timeout(self, started: float) -> None:
        if self._config.timeout_seconds <= 0:
            return
        if (time.monotonic() - started) > self._config.timeout_seconds:
            raise InternalOcrTimeoutError(
                f"internal OCR exceeded {self._config.timeout_seconds}s budget"
            )

    def _remaining_timeout(self, started: float) -> int:
        if self._config.timeout_seconds <= 0:
            return 30
        remaining = self._config.timeout_seconds - (time.monotonic() - started)
        return max(1, int(remaining))

    def _build_evidence(
        self,
        *,
        normalized: NormalizedOcrLabel,
        read: InternalOcrReadResult,
        variant_name: str,
        variants_attempted: int,
        variants_succeeded: int,
        variant_failures: list[dict[str, Any]],
        preprocess_ms: int,
        engine_ms: int,
    ) -> dict[str, Any]:
        text_hash = hashlib.sha256(
            (read.full_text or "").encode("utf-8", errors="replace")
        ).hexdigest()
        return {
            "processor_name": PROCESSOR_NAME,
            "processor_version": PROCESSOR_VERSION,
            "engine_name": read.engine_name,
            "engine_version": read.engine_version,
            "preprocessing_variant": variant_name,
            "selected_variant": variant_name,
            "variants_attempted": variants_attempted,
            "variants_succeeded": variants_succeeded,
            "variant_failures": variant_failures,
            "ocr_preprocessing_duration_ms": preprocess_ms,
            "ocr_engine_duration_ms": engine_ms,
            "confidence": read.confidence,
            "confidence_threshold": self._config.min_aggregate_confidence,
            "full_text_sha256": text_hash,
            "text_block_count": len(read.text_blocks),
            "selected_code_rule": normalized.selected_code_rule,
            "selected_qty_rule": normalized.selected_qty_rule,
            "warnings": list(normalized.warnings)[:20],
        }

    def _result_via_profile(
        self,
        *,
        context: ImageProcessingContext,
        mode: str,
        extraction: OcrFieldExtraction,
        evidence: dict[str, Any],
        duration_ms: int,
        profile_cfg: ExtractionProfileConfiguration,
    ) -> ImageProcessingResult:
        mapper = OcrCandidateToFieldCandidateMapper()
        stage = "CANDIDATE_MAPPING"
        try:
            self._emit(
                context,
                "ocr.candidate_mapping_started",
                message="mapping OCR candidates to field candidates",
                metadata={
                    "code_candidates_count": len(extraction.internal_code_candidates),
                    "quantity_candidates_count": len(extraction.quantity_candidates),
                },
            )
            code_candidates = mapper.map_code_list(
                list(extraction.internal_code_candidates)
                + list(extraction.ean_candidates)
                + list(extraction.article_candidates)
                + list(extraction.product_candidates)
            )
            qty_candidates = mapper.map_quantity_list(list(extraction.quantity_candidates))
            additional: dict[str, str] = {}
            if extraction.lot_candidates:
                additional["lote"] = extraction.lot_candidates[0].value
            if extraction.expiration_candidates:
                additional["vencimiento"] = extraction.expiration_candidates[0].value
            self._emit(
                context,
                "ocr.candidate_mapping_completed",
                message="OCR candidate mapping completed",
                metadata={
                    "code_candidates_count": len(code_candidates),
                    "quantity_candidates_count": len(qty_candidates),
                },
            )

            stage = "PROFILE_VALIDATION"
            self._emit(
                context,
                "profile.validation_started",
                message="profile-aware validation started",
                metadata={
                    "code_candidates_count": len(code_candidates),
                    "quantity_candidates_count": len(qty_candidates),
                },
            )
            safe_evidence = serialize_ocr_candidate_evidence(dict(evidence or {}))
            if not isinstance(safe_evidence, dict):
                safe_evidence = {}
            if getattr(context, "_ocr_observability_incomplete", False):
                safe_evidence = {
                    **safe_evidence,
                    "observability_incomplete": True,
                }
            result = apply_profile_validation(
                job_id=context.job_id,
                asset_id=context.asset_id,
                processing_mode=mode,
                resolved_by=STRATEGY_KEY,
                candidates=FieldCandidateSet(
                    code_candidates=code_candidates,
                    quantity_candidates=qty_candidates,
                    additional_fields=additional,
                    evidence=safe_evidence,
                    warnings=list(extraction.warnings),
                ),
                configuration=profile_cfg,
                duration_ms=duration_ms,
                provider_name=PROCESSOR_NAME,
                model_name=self.attempt_model,
            )
            if result.status is ImageResultStatus.RESOLVED_INTERNAL:
                self._metrics.increment("ocr_resolved_total")
            validation_errors = list(result.validation_errors or [])
            self._emit(
                context,
                "profile.validation_completed",
                message="profile-aware validation completed",
                error_code=result.error_code,
                duration_ms=duration_ms,
                metadata={
                    "status": getattr(result.status, "value", str(result.status)),
                    "internal_code_status": ("present" if result.internal_code else "missing"),
                    "quantity_status": ("present" if result.quantity is not None else "missing"),
                    "validation_errors": validation_errors[:20],
                    "error_code": result.error_code,
                },
            )
            return result
        except ExtractionProfileConfigurationError as exc:
            self._emit(
                context,
                "asset.processing_failed",
                message="invalid extraction profile snapshot",
                error_code="PROFILE_SNAPSHOT_INVALID",
                severity="ERROR",
                metadata={
                    "stage": stage,
                    "exception_type": type(exc).__name__,
                    "safe_message": str(getattr(exc, "message", exc))[:200],
                    "code_candidates_count": len(extraction.internal_code_candidates),
                    "quantity_candidates_count": len(extraction.quantity_candidates),
                },
            )
            return self._technical(
                context,
                mode,
                "PROFILE_SNAPSHOT_INVALID",
                str(getattr(exc, "message", exc)),
                time.monotonic() - (duration_ms / 1000.0),
                evidence=serialize_ocr_candidate_evidence(evidence)
                if isinstance(evidence, dict)
                else {},
            )
        except Exception as exc:
            logger.exception(
                "internal_ocr.profile_path_failed job_id=%s asset_id=%s stage=%s",
                context.job_id,
                context.asset_id,
                stage,
            )
            self._emit(
                context,
                "asset.processing_failed",
                message="profile validation path failed",
                error_code="INTERNAL_OCR_STRATEGY_EXCEPTION",
                severity="ERROR",
                metadata={
                    "stage": stage,
                    "exception_type": type(exc).__name__,
                    "code_candidates_count": len(extraction.internal_code_candidates),
                    "quantity_candidates_count": len(extraction.quantity_candidates),
                },
            )
            # Do not normalize programming defects into a successful functional path.
            raise

    def _emit_asset_finalized(
        self, context: ImageProcessingContext, result: ImageProcessingResult
    ) -> None:
        flags = getattr(context, "__dict__", None)
        if isinstance(flags, dict) and flags.get("_ocr_asset_finalized"):
            return
        if isinstance(flags, dict):
            flags["_ocr_asset_finalized"] = True
        status_value = getattr(result.status, "value", str(result.status))
        meta: dict[str, Any] = {
            "status": status_value,
            "validation_errors": list(result.validation_errors or [])[:20],
        }
        if isinstance(flags, dict) and flags.get("_ocr_observability_incomplete"):
            meta["observability_incomplete"] = True
        self._emit(
            context,
            "asset.finalized",
            message=f"asset finalized as {status_value}",
            error_code=result.error_code,
            duration_ms=result.processing_duration_ms,
            severity=("ERROR" if result.status is ImageResultStatus.FAILED_TECHNICAL else "INFO"),
            metadata=meta,
        )

    def _technical(
        self,
        context: ImageProcessingContext,
        mode: str,
        error_code: str,
        message: str,
        started: float,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> ImageProcessingResult:
        # Sole increment site for this counter — callers must not increment it themselves,
        # or every technical failure would be double-counted in metrics.
        self._metrics.increment("ocr_technical_failures_total")
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "internal_ocr.technical job_id=%s asset_id=%s error_code=%s",
            context.job_id,
            context.asset_id,
            error_code,
        )
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=mode,
            resolved_by=STRATEGY_KEY,
            error_code=error_code,
            error_message=message[:500],
            evidence=evidence,
            provider_name=PROCESSOR_NAME,
            model_name=self.attempt_model,
            processing_duration_ms=duration_ms,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


__all__ = [
    "InternalOcrConfig",
    "InternalOcrMetrics",
    "InternalOcrProcessingStrategy",
    "InternalOcrTimeoutError",
    "PROCESSOR_NAME",
    "PROCESSOR_VERSION",
    "STRATEGY_KEY",
]
