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
from typing import Any

from src.application.ports.internal_label_reader import (
    InternalLabelReader,
    InternalOcrContext,
    InternalOcrEngineTimeoutError,
    InternalOcrEngineUnavailableError,
    InternalOcrReadResult,
)
from src.application.services.image_processing.ocr_field_extractor import OcrFieldExtractor
from src.application.services.image_processing.ocr_image_preprocessor import (
    OcrImagePreprocessor,
)
from src.application.services.image_processing.ocr_result_normalizer import (
    NormalizedOcrLabel,
    OcrClientFieldRules,
    OcrNormalizeStatus,
    OcrResultNormalizer,
)
from src.domain.assets.entities import SourceAsset
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


class SourceAssetContentReaderPort:
    def read_image_bytes(self, asset: SourceAsset) -> bytes: ...  # pragma: no cover


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
    ) -> None:
        self._reader = reader
        self._content_reader = content_reader
        self._preprocessor = preprocessor
        self._extractor = extractor
        self._normalizer = normalizer
        self._config = config
        self._metrics = metrics or InternalOcrMetrics()

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

    def process(
        self, context: ImageProcessingContext, asset: SourceAsset
    ) -> ImageProcessingResult:
        started = time.monotonic()
        mode = getattr(context.identification_mode, "value", str(context.identification_mode))
        self._metrics.increment("ocr_images_total")

        try:
            content = self._content_reader.read_image_bytes(asset)
        except FileNotFoundError as exc:
            return self._technical(context, mode, "SOURCE_ASSET_NOT_FOUND", str(exc), started)
        except Exception as exc:
            return self._technical(context, mode, "SOURCE_ASSET_READ_FAILED", str(exc), started)

        if not content:
            return self._technical(
                context, mode, "SOURCE_ASSET_EMPTY", "empty source asset content", started
            )

        try:
            variants = self._preprocessor.prepare_variants(content)
        except ValueError as exc:
            return self._technical(context, mode, "OCR_IMAGE_DECODE_FAILED", str(exc), started)
        except Exception as exc:
            return self._technical(context, mode, "OCR_PREPROCESS_FAILED", str(exc), started)

        best: tuple[NormalizedOcrLabel, InternalOcrReadResult, str, int] | None = None
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
                ocr_ctx = InternalOcrContext(
                    job_id=context.job_id,
                    asset_id=context.asset_id,
                    client_id=context.client_id,
                    language=self._config.language,
                    timeout_seconds=float(self._remaining_timeout(started)),
                    max_image_dimension=self._config.max_image_dimension,
                )
                try:
                    read = self._reader.read(prepared, ocr_ctx)
                except InternalOcrEngineTimeoutError as exc:
                    # Hard technical failure: bail out immediately (do not keep trying
                    # variants against a wall-clock budget that has already been blown).
                    return self._technical(
                        context, mode, "INTERNAL_OCR_TIMEOUT", str(exc), started
                    )
                except InternalOcrEngineUnavailableError as exc:
                    return self._technical(
                        context,
                        mode,
                        "INTERNAL_OCR_ENGINE_UNAVAILABLE",
                        str(exc),
                        started,
                    )
                except Exception as exc:
                    # Soft-fail this variant; try next if any remain.
                    variant_records.append(
                        _VariantAttempt(
                            variant_name=prepared.variant_name,
                            duration_ms=int((time.monotonic() - variant_started) * 1000),
                            error_code="OCR_VARIANT_EXCEPTION",
                            error_type=type(exc).__name__,
                        )
                    )
                    logger.warning(
                        "internal_ocr.variant_failed job_id=%s asset_id=%s variant=%s err=%s",
                        context.job_id,
                        context.asset_id,
                        prepared.variant_name,
                        exc,
                    )
                    continue

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
                extraction = self._extractor.extract(read)
                normalized = self._normalizer.normalize(extraction)

                candidate = normalized
                if normalized.status is OcrNormalizeStatus.RESOLVED:
                    if self._confidence_ok(read):
                        best = (normalized, read, prepared.variant_name, variants_attempted)
                        break
                    # Confidence gate failed: never accept this as the resolved answer.
                    # Build a fresh PENDING_MANUAL_REVIEW candidate instead of mutating
                    # `normalized` in place, so the rejected RESOLVED label is never the one
                    # that ends up driving the final (accepted) result below.
                    candidate = self._demote_low_confidence(normalized)
                    self._metrics.increment("ocr_low_confidence_total")

                if best is None or self._rank(candidate) < self._rank(best[0]):
                    best = (candidate, read, prepared.variant_name, variants_attempted)
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
                quantity=float(normalized.quantity)
                if normalized.quantity is not None
                else None,
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
            if "QUANTITY_MISSING" in normalized.validation_errors:
                self._metrics.increment("ocr_missing_quantity_total")
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
