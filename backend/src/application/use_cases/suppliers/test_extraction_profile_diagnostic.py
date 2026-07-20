"""Diagnostic dry-run for supplier extraction profiles (no inventory persistence)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.ports.internal_label_reader import InternalOcrContext, PreparedImage
from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.image_processing.field_candidate_set import (
    FieldCandidateSet,
    apply_profile_validation,
)
from src.application.services.image_processing.label_geometry_normalizer import (
    LabelGeometryNormalizer,
)
from src.application.services.image_processing.label_region_detector import (
    LabelRegionDetector,
)
from src.application.services.image_processing.ocr_candidate_filters import (
    filter_internal_code_candidate,
)
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldExtractor,
    OcrFieldKind,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)
from src.config import load_settings


@dataclass(frozen=True)
class TestExtractionProfileCommand:
    client_id: str
    supplier_id: str
    configuration: dict[str, Any]
    image_bytes: bytes
    max_bytes: int = 8_000_000


class TestExtractionProfileUseCase:
    """Run detector + OCR + profile validation diagnostically without creating positions."""

    def execute(self, command: TestExtractionProfileCommand) -> dict[str, Any]:
        settings = load_settings()
        if not bool(getattr(settings, "ocr_profile_test_tool_enabled", False)):
            raise PermissionError("OCR_PROFILE_TEST_TOOL_DISABLED")
        if not command.image_bytes:
            raise ValueError("IMAGE_REQUIRED")
        if len(command.image_bytes) > int(command.max_bytes):
            raise ValueError("IMAGE_TOO_LARGE")

        try:
            config = parse_extraction_configuration(command.configuration)
        except ExtractionProfileConfigurationError as exc:
            raise ValueError(f"PROFILE_INVALID:{exc.code}") from exc

        detection = LabelRegionDetector(
            rules=config.label_detection_rules,
            light_ocr_reader=None,
        ).detect(command.image_bytes)
        selected = detection.selected_candidate
        geom = LabelGeometryNormalizer(
            allow_perspective_correction=config.label_detection_rules.allow_perspective_correction,
        ).normalize_region(
            command.image_bytes,
            selected,
            allow_full_image_fallback=config.label_detection_rules.allow_full_image_fallback,
        )

        rejected: list[dict[str, Any]] = []
        ocr_meta: dict[str, Any] = {"executed": False}
        code_candidates: list[FieldCandidate] = []
        qty_candidates: list[FieldCandidate] = []

        try:
            from src.infrastructure.ocr.tesseract_internal_label_reader import (
                TesseractInternalLabelReader,
            )

            lang = str(getattr(settings, "internal_ocr_language", "spa+eng") or "spa+eng")
            reader = TesseractInternalLabelReader(default_language=lang)
            prepared = PreparedImage(
                content=geom.image_bytes,
                width=geom.width,
                height=geom.height,
                variant_name="profile_test",
            )
            read = reader.read(
                prepared,
                InternalOcrContext(
                    job_id="profile-test",
                    asset_id="profile-test",
                    client_id=command.client_id,
                    language=lang,
                    timeout_seconds=min(
                        15.0, float(getattr(settings, "internal_ocr_timeout_seconds", 20))
                    ),
                    max_image_dimension=int(
                        getattr(settings, "internal_ocr_max_image_dimension", 2048)
                    ),
                    page_segmentation_mode=6,
                ),
            )
            extraction = OcrFieldExtractor().extract(read)
            ocr_meta = {
                "executed": True,
                "engine": read.engine_name,
                "engine_version": read.engine_version,
                "text_block_count": len(read.text_blocks),
                "average_confidence": read.confidence,
                "duration_ms": read.duration_ms,
            }
            for c in extraction.internal_code_candidates:
                decision = filter_internal_code_candidate(
                    c.value, rules=config.validation_rules.code, neighbor_text=c.associated_text
                )
                if not decision.accepted:
                    rejected.append(
                        {
                            "field": "internal_code",
                            "masked_candidate": (c.value[:3] + "***") if len(c.value) > 3 else "***",
                            "source": c.source,
                            "reason_code": decision.reason_code,
                            "rule": decision.rule,
                        }
                    )
                    continue
                code_candidates.append(
                    FieldCandidate(
                        source_key="INTERNAL_CODE",
                        value=c.value,
                        evidence_score=float(c.confidence or 0.5),
                        labeled=True,
                    )
                )
            for c in extraction.ean_candidates:
                code_candidates.append(
                    FieldCandidate(
                        source_key="EAN",
                        value=c.value,
                        evidence_score=float(c.confidence or 0.5),
                        labeled=c.kind is OcrFieldKind.EAN,
                    )
                )
            qty_candidates = [
                FieldCandidate(
                    source_key="QUANTITY",
                    value=c.value,
                    evidence_score=float(c.confidence or 0.5),
                )
                for c in extraction.quantity_candidates
            ]
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            ImportError,
        ) as exc:
            from src.application.ports.internal_label_reader import (
                InternalOcrEngineTimeoutError,
                InternalOcrEngineUnavailableError,
            )

            if isinstance(
                exc, (InternalOcrEngineTimeoutError, InternalOcrEngineUnavailableError)
            ):
                ocr_meta = {
                    "executed": False,
                    "error_type": type(exc).__name__,
                    "error_code": (
                        "OCR_ENGINE_UNAVAILABLE"
                        if isinstance(exc, InternalOcrEngineUnavailableError)
                        else "OCR_ENGINE_TIMEOUT"
                    ),
                }
            else:
                ocr_meta = {
                    "executed": False,
                    "error_type": type(exc).__name__,
                    "error_code": "OCR_DIAGNOSTIC_FAILED",
                }

        result = apply_profile_validation(
            job_id="profile-test",
            asset_id="profile-test",
            processing_mode="INTERNAL_OCR",
            resolved_by="PROFILE_TEST",
            candidates=FieldCandidateSet(
                code_candidates=code_candidates,
                quantity_candidates=qty_candidates,
            ),
            configuration=config,
            duration_ms=int(ocr_meta.get("duration_ms") or 0),
            provider_name="profile_test",
            model_name="diagnostic",
        )

        expected_status = result.status.value if hasattr(result.status, "value") else str(result.status)
        return {
            "client_id": command.client_id,
            "supplier_id": command.supplier_id,
            "label_detected": detection.detected,
            "selected_relative_area": (
                selected.relative_area if selected is not None else None
            ),
            "matched_anchors": list(selected.matched_anchors) if selected else [],
            "candidate_count": len(detection.candidates),
            "geometry": {
                "width": geom.width,
                "height": geom.height,
                "perspective_corrected": geom.perspective_corrected,
                "applied_rotation_deg": geom.applied_rotation_deg,
                "used_original_region": geom.used_original_region,
            },
            "ocr": ocr_meta,
            "code_candidate": result.internal_code,
            "quantity_candidate": result.quantity,
            "rejected_candidates": rejected,
            "validation_errors": list(result.validation_errors or []),
            "expected_status": expected_status,
            "error_code": result.error_code,
            "profile_rules_applied": {
                "exact_length": config.validation_rules.code.exact_length,
                "reject_measurement_patterns": (
                    config.validation_rules.code.reject_measurement_patterns
                ),
                "missing_quantity_action": (
                    config.quantity_rules.missing_quantity_action.value
                ),
            },
            "persists_inventory": False,
        }


__all__ = [
    "TestExtractionProfileCommand",
    "TestExtractionProfileUseCase",
]
