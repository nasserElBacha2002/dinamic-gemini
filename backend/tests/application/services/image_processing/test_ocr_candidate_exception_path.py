"""Regression tests for OCR candidate mapping / ranking / profile path (zero / one / many)."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO

from PIL import Image

from src.application.ports.internal_label_reader import (
    InternalOcrContext,
    InternalOcrReadResult,
    OcrTextBlock,
    PreparedImage,
)
from src.application.services.image_processing.field_candidate_set import (
    apply_profile_validation,
)
from src.application.services.image_processing.internal_ocr_processing_strategy import (
    InternalOcrConfig,
    InternalOcrProcessingStrategy,
)
from src.application.services.image_processing.ocr_candidate_ranker import (
    rank_code_candidates,
    score_field_candidate,
)
from src.application.services.image_processing.ocr_candidate_to_field_candidate_mapper import (
    OcrCandidateToFieldCandidateMapper,
    serialize_ocr_candidate_evidence,
)
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldCandidate,
    OcrFieldExtractor,
    OcrFieldKind,
)
from src.application.services.image_processing.ocr_image_preprocessor import (
    OcrImagePreprocessor,
    OcrPreprocessConfig,
)
from src.application.services.image_processing.ocr_result_normalizer import OcrResultNormalizer
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_metadata,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.extraction_profile import (
    inventory_seven_digit_internal_code_template,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)


def _jsonable(obj):
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (200, 80), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


class _BytesReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


class _RecordingEvents:
    def __init__(self) -> None:
        self.events: list[str] = []

    def publish(self, **kwargs) -> None:
        self.events.append(str(kwargs.get("event_type")))


class _FakeReader:
    engine_name = "fake"
    engine_version = "1"

    def __init__(self, blocks: tuple[OcrTextBlock, ...], full_text: str) -> None:
        self._blocks = blocks
        self._full_text = full_text

    def read(self, image: PreparedImage, context: InternalOcrContext) -> InternalOcrReadResult:
        return InternalOcrReadResult(
            full_text=self._full_text,
            text_blocks=self._blocks,
            confidence=85.0,
            orientation=0,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            duration_ms=5,
        )


def _asset(asset_id: str = "asset-1") -> SourceAsset:
    return SourceAsset(
        id=asset_id,
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{asset_id}.jpg",
        storage_path=f"/{asset_id}.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _context(*, asset_id: str = "asset-1") -> ImageProcessingContext:
    cfg = _jsonable(inventory_seven_digit_internal_code_template())
    return ImageProcessingContext(
        job_id="job-1",
        asset_id=asset_id,
        aisle_id="aisle-1",
        inventory_id="inv-1",
        client_id=None,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
        execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        supplier_extraction_profile={"configuration": cfg},
        profile_aware_validation_enabled=True,
    )


def _strategy(reader, events: _RecordingEvents | None = None) -> InternalOcrProcessingStrategy:
    return InternalOcrProcessingStrategy(
        reader=reader,
        content_reader=_BytesReader(_png()),
        preprocessor=OcrImagePreprocessor(
            OcrPreprocessConfig(max_variants=1, enable_adaptive_threshold=False)
        ),
        extractor=OcrFieldExtractor(),
        normalizer=OcrResultNormalizer(quantity_max=9999),
        config=InternalOcrConfig(
            quantity_max=9999,
            max_variants=1,
            timeout_seconds=30,
            diagnostic_evidence_enabled=True,
            label_detection_enabled=False,
        ),
        event_publisher=events,
    )


def test_zero_candidates_unrecognized_missing_internal_code() -> None:
    from src.application.services.image_processing.field_candidate_set import FieldCandidateSet

    result = apply_profile_validation(
        job_id="j",
        asset_id="a",
        processing_mode="INTERNAL_OCR",
        resolved_by="INTERNAL_OCR",
        candidates=FieldCandidateSet(code_candidates=[], quantity_candidates=[]),
        configuration=inventory_seven_digit_internal_code_template(),
        duration_ms=1,
    )
    assert result.status is ImageResultStatus.UNRECOGNIZED
    assert result.error_code == "MISSING_INTERNAL_CODE"


def test_one_code_without_quantity_pending_manual_review() -> None:
    from src.application.services.image_processing.field_candidate_set import FieldCandidateSet

    result = apply_profile_validation(
        job_id="j",
        asset_id="a",
        processing_mode="INTERNAL_OCR",
        resolved_by="INTERNAL_OCR",
        candidates=FieldCandidateSet(
            code_candidates=[
                FieldCandidate(
                    source_key="INTERNAL_CODE",
                    value="1428706",
                    evidence_score=0.9,
                    labeled=False,
                    extraction_method="NUMERIC_PATTERN",
                )
            ],
            quantity_candidates=[],
        ),
        configuration=inventory_seven_digit_internal_code_template(),
        duration_ms=1,
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == "MISSING_QUANTITY"
    assert result.internal_code == "1428706"


def test_equivalent_codes_deduped_not_ambiguous() -> None:
    decision = rank_code_candidates(
        [
            FieldCandidate(
                source_key="INTERNAL_CODE",
                value="1428706",
                evidence_score=0.9,
                extraction_method="LABELED_EXACT",
            ),
            FieldCandidate(
                source_key="INTERNAL_CODE",
                value="1428706",
                evidence_score=0.4,
                extraction_method="NUMERIC_PATTERN",
            ),
        ]
    )
    assert decision.ambiguous is False
    assert decision.winner is not None
    assert decision.winner.value == "1428706"


def test_distinct_codes_ambiguous_without_margin() -> None:
    decision = rank_code_candidates(
        [
            FieldCandidate(
                source_key="INTERNAL_CODE",
                value="1428706",
                evidence_score=0.55,
                extraction_method="NUMERIC_PATTERN",
            ),
            FieldCandidate(
                source_key="INTERNAL_CODE",
                value="1428708",
                evidence_score=0.54,
                extraction_method="NUMERIC_PATTERN",
            ),
        ]
    )
    assert decision.ambiguous is True
    assert decision.winner is None


def test_none_optional_fields_do_not_break_scoring() -> None:
    cand = FieldCandidate(
        source_key="INTERNAL_CODE",
        value="1428706",
        evidence_score=0.5,
        extraction_method=None,
        spatial_relation=None,
        normalized_distance=None,
        anchor_text=None,
    )
    assert score_field_candidate(cand) >= 0.0


def test_serialize_ocr_candidate_evidence_primitives() -> None:
    from src.application.services.image_processing.ocr_spatial_relation_evaluator import (
        BoundingBox,
    )

    payload = {
        "enum": OcrFieldKind.INTERNAL_CODE,
        "bbox": BoundingBox(1, 2, 3, 4),
        "tuple": (1, 2, 3),
        "dc": OcrFieldCandidate(
            kind=OcrFieldKind.INTERNAL_CODE,
            value="1428706",
            source="numeric_pattern",
            associated_text="",
            confidence=None,
            region=(1, 2, 3, 4),
            rule="numeric_pattern",
        ),
    }
    serialized = serialize_ocr_candidate_evidence(payload)
    json.dumps(serialized)


def test_mapper_handles_optional_confidence() -> None:
    mapper = OcrCandidateToFieldCandidateMapper()
    mapped = mapper.map_code(
        OcrFieldCandidate(
            kind=OcrFieldKind.INTERNAL_CODE,
            value="1428706",
            source="numeric_pattern",
            associated_text="",
            confidence=None,
            region=None,
            rule="numeric_pattern",
            extraction_method="NUMERIC_PATTERN",
            normalized_distance=None,
        )
    )
    assert mapped is not None
    assert mapped.evidence_score == 0.5
    assert mapped.labeled is False


def test_asset_a_all_rejected_no_exception() -> None:
    # Junk tokens → after filter 0 codes.
    blocks = tuple(
        OcrTextBlock(
            text=t,
            confidence=80,
            left=0,
            top=i * 10,
            width=40,
            height=10,
            block_num=1,
            line_num=i,
        )
        for i, t in enumerate(["60x60", "600", "mm", "26", "abc"] * 10)
    )
    events = _RecordingEvents()
    result = _strategy(_FakeReader(blocks, "junk"), events).process(_context(), _asset())
    assert result.status is ImageResultStatus.UNRECOGNIZED
    assert result.error_code == "MISSING_INTERNAL_CODE"
    assert "profile.validation_completed" in events.events
    assert "asset.finalized" in events.events
    assert "asset.processing_failed" not in events.events


def test_asset_c_three_codes_no_qty_no_exception() -> None:
    blocks = (
        OcrTextBlock(text="CODIGO", confidence=90, left=10, top=10, width=50, height=12, block_num=1, line_num=1),
        OcrTextBlock(text="INTERNO", confidence=90, left=65, top=10, width=60, height=12, block_num=1, line_num=1),
        OcrTextBlock(text="1428706", confidence=92, left=20, top=40, width=80, height=16, block_num=1, line_num=2),
        OcrTextBlock(text="1428706", confidence=80, left=20, top=60, width=80, height=16, block_num=1, line_num=3),
        OcrTextBlock(text="1428708", confidence=70, left=20, top=80, width=80, height=16, block_num=1, line_num=4),
    )
    events = _RecordingEvents()
    result = _strategy(_FakeReader(blocks, "CODIGO INTERNO\n1428706\n1428706\n1428708"), events).process(
        _context(asset_id="asset-c"), _asset("asset-c")
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code in {"MISSING_QUANTITY", "AMBIGUOUS_INTERNAL_CODE"}
    assert "ocr.candidate_mapping_started" in events.events
    assert "ocr.candidate_mapping_completed" in events.events
    assert "profile.validation_started" in events.events
    assert "profile.validation_completed" in events.events
    assert "asset.finalized" in events.events


def test_sanitizer_keeps_ocr_counters() -> None:
    meta = sanitize_metadata(
        {
            "normalized_token_count": 12,
            "numeric_token_count": 3,
            "code_before_filter": 48,
            "code_after_filter": 0,
            "rejection_reasons": {"CODE_LENGTH_NOT_EXACT": 22},
        },
        level="TECHNICAL_SAFE",
    )
    assert meta["normalized_token_count"] == 12
    assert meta["code_after_filter"] == 0
    assert meta["rejection_reasons"]["CODE_LENGTH_NOT_EXACT"] == 22


def test_anchors_preferred_in_seven_digit_template() -> None:
    from src.domain.client_supplier.extraction_profile import AnchorMatchPolicy

    cfg = inventory_seven_digit_internal_code_template()
    assert (
        cfg.label_detection_rules.anchor_match_policy
        is AnchorMatchPolicy.ANCHORS_PREFERRED
    )
