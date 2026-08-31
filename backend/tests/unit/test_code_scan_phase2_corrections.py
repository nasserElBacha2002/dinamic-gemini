"""Phase 2 corrections — CODE_SCAN classifier, materialization, regex, fail-closed."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.application.services.label_validation import (
    LabelProfileConfigurationError,
    LabelValidationContext,
    LabelValidationService,
    compile_payload_pattern,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    QrPayloadFormat,
)
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import ImageProcessingContext, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
)
from src.domain.product_labels.format import (
    build_product_label_payload,
    generate_product_label_id,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


class _Reader:
    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return b"fake-image"


class _Scanner:
    def __init__(self, *values: str) -> None:
        self._values = values

    @property
    def engine_name(self) -> str:
        return "test"

    def scan_asset(self, asset, content=None):
        return [
            CodeScanDetectionCandidate(
                code_type=CodeType.BARCODE,
                code_value=v,
                confidence=1.0,
                bounding_box_json=None,
                metadata_json={"pyzbar_type": "CODE128"},
            )
            for v in self._values
        ]


def _profiles(
    *,
    item: LabelProfileSource = LabelProfileSource.SUPPLIER,
    position: LabelProfileSource = LabelProfileSource.SUPPLIER,
    item_version: int = 1,
    position_version: int = 1,
) -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=item,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_id="ep-item",
            extraction_profile_version=item_version,
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=position,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_id="ep-pos",
            extraction_profile_version=position_version,
        ),
    )


def _item_cfg(pattern: str, *, required: tuple[str, ...] = ("internal_code",)) -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        accepted_barcode_formats=("CODE128", "QR"),
        custom_payload_pattern=pattern,
        required_fields=required,
        qr_payload_formats=(
            QrPayloadFormat.PLAIN_CODE.value,
            QrPayloadFormat.CODE_QUANTITY_PIPE.value,
        ),
    )


def _pos_cfg(pattern: str, *, required: tuple[str, ...] = ()) -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        accepted_barcode_formats=("CODE128", "QR"),
        custom_payload_pattern=pattern,
        required_fields=required,
    )


def _ctx(validation_ctx: LabelValidationContext) -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job-1",
        asset_id="asset-1",
        aisle_id="aisle-1",
        inventory_id="inv-1",
        client_id="client-1",
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        label_validation_context=validation_ctx,
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=_NOW,
        upload_client_file_id="cf1",
    )


def _strategy(
    *values: str,
    repo: MemoryImagePositionLabelDetectionRepository | None = None,
) -> CodeScanProcessingStrategy:
    parser = EncodedLabelPayloadParser(quantity_max=9999)
    return CodeScanProcessingStrategy(
        scanner=_Scanner(*values),
        content_reader=_Reader(),
        parser=parser,
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=MagicMock(),
        label_validation_service=LabelValidationService(),
        position_detection=None,
        position_label_detection_repo=repo,
    )


def test_supplier_item_valid_invalid_duplicate_symbology_pattern_quantity() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(r"^SUP[0-9]{8}$"),
        position_extraction_configuration=_pos_cfg(r"^POS-[A-Z0-9]+$"),
        job_id="job-1",
        client_id="client-1",
    )
    ok = _strategy("SUP12345678", repo=repo).process(_ctx(ctx), _asset())
    assert ok.status is ImageResultStatus.RESOLVED_INTERNAL

    bad = _strategy("NOPE", repo=repo).process(_ctx(ctx), _asset())
    assert bad.status is ImageResultStatus.UNRECOGNIZED

    dup = _strategy("SUP12345678", "SUP12345678", repo=repo).process(_ctx(ctx), _asset())
    assert dup.status is ImageResultStatus.RESOLVED_INTERNAL
    assert len(dup.product_results) == 1

    qty_required = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(
            r"^SUP[0-9]{8}$", required=("internal_code", "quantity")
        ),
        position_extraction_configuration=_pos_cfg(r"^POS-X$"),
        job_id="job-1",
    )
    missing_qty = _strategy("SUP12345678").process(_ctx(qty_required), _asset())
    assert missing_qty.status is not ImageResultStatus.RESOLVED_INTERNAL


def test_supplier_position_materialized_and_only_position_not_unrecognized() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(r"^SUP[0-9]{8}$"),
        position_extraction_configuration=_pos_cfg(r"^POS-[A-Z0-9]+$"),
        job_id="job-1",
        client_id="client-1",
    )
    result = _strategy("POS-RACK01", repo=repo).process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == "POSITION_LABEL_ONLY"
    assert result.status is not ImageResultStatus.UNRECOGNIZED
    stored = list(repo.list_by_asset("job-1", "asset-1"))
    assert len(stored) == 1
    assert stored[0].public_identifier == "POS-RACK01"
    assert stored[0].metadata_json.get("profile_source") == "SUPPLIER"
    assert (result.evidence or {}).get("position_label_detection", {}).get(
        "normalized_positions"
    )


def test_supplier_position_plus_item() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(r"^SUP[0-9]{8}$"),
        position_extraction_configuration=_pos_cfg(r"^POS-[A-Z0-9]+$"),
        job_id="job-1",
        client_id="client-1",
    )
    result = _strategy("POS-RACK01", "SUP12345678", repo=repo).process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert len(result.product_results) == 1
    assert len(list(repo.list_by_asset("job-1", "asset-1"))) == 1


def test_ambiguity_no_silent_winner() -> None:
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(r"^ABC[0-9]+$"),
        position_extraction_configuration=_pos_cfg(r"^ABC[0-9]+$"),
        job_id="job-1",
    )
    result = _strategy("ABC123").process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value


def test_snapshot_job_a_v1_job_b_v2_item_observable() -> None:
    """Job A keeps V1 accept; Job B uses V2 reject for same payload."""
    v1 = LabelValidationContext(
        resolved_profiles=_profiles(item_version=1),
        item_extraction_configuration=_item_cfg(r"^SKU-V1$"),
        position_extraction_configuration=_pos_cfg(r"^POS-NEVER$"),
        job_id="job-a",
    )
    v2 = LabelValidationContext(
        resolved_profiles=_profiles(item_version=2),
        item_extraction_configuration=_item_cfg(r"^SKU-V2$"),
        position_extraction_configuration=_pos_cfg(r"^POS-NEVER$"),
        job_id="job-b",
    )
    a = _strategy("SKU-V1").process(_ctx(v1), _asset())
    b = _strategy("SKU-V1").process(_ctx(v2), _asset())
    assert a.status is ImageResultStatus.RESOLVED_INTERNAL
    assert b.status is not ImageResultStatus.RESOLVED_INTERNAL


def test_snapshot_job_a_v1_job_b_v2_position_observable() -> None:
    repo_a = MemoryImagePositionLabelDetectionRepository()
    repo_b = MemoryImagePositionLabelDetectionRepository()
    v1 = LabelValidationContext(
        resolved_profiles=_profiles(position_version=1),
        item_extraction_configuration=_item_cfg(r"^ITEM-NEVER$"),
        position_extraction_configuration=_pos_cfg(r"^POS-V1$"),
        job_id="job-a",
    )
    v2 = LabelValidationContext(
        resolved_profiles=_profiles(position_version=2),
        item_extraction_configuration=_item_cfg(r"^ITEM-NEVER$"),
        position_extraction_configuration=_pos_cfg(r"^POS-V2$"),
        job_id="job-b",
    )
    a = _strategy("POS-V1", repo=repo_a).process(
        ImageProcessingContext(
            job_id="job-a",
            asset_id="asset-1",
            aisle_id="aisle-1",
            inventory_id="inv-1",
            client_id="client-1",
            identification_mode=AisleIdentificationMode.CODE_SCAN,
            execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
            configuration_snapshot_version=1,
            provider_name=None,
            model_name=None,
            prompt_key=None,
            prompt_version=None,
            attempt_number=1,
            label_validation_context=v1,
        ),
        _asset(),
    )
    b = _strategy("POS-V1", repo=repo_b).process(
        ImageProcessingContext(
            job_id="job-b",
            asset_id="asset-1",
            aisle_id="aisle-1",
            inventory_id="inv-1",
            client_id="client-1",
            identification_mode=AisleIdentificationMode.CODE_SCAN,
            execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
            configuration_snapshot_version=1,
            provider_name=None,
            model_name=None,
            prompt_key=None,
            prompt_version=None,
            attempt_number=1,
            label_validation_context=v2,
        ),
        _asset(),
    )
    assert a.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert len(list(repo_a.list_by_asset("job-a", "asset-1"))) == 1
    assert b.status is ImageResultStatus.UNRECOGNIZED
    assert list(repo_b.list_by_asset("job-b", "asset-1")) == []


def test_valid_d1_under_supplier_is_source_mismatch_not_format_invalid() -> None:
    label_id = generate_product_label_id()
    payload = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload=payload, symbology="QR_CODE"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(item=LabelProfileSource.SUPPLIER),
            item_extraction_configuration=_item_cfg(r"^D1\|.*$"),
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value


def test_code_scan_fail_closed_invalid_checksum_under_supplier() -> None:
    label_id = generate_product_label_id()
    payload = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    bad = payload[:-1] + ("0" if payload[-1] != "0" else "1")
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(r"^D1\|.*$"),
        position_extraction_configuration=_pos_cfg(r"^POS-NEVER$"),
        job_id="job-1",
    )
    result = _strategy(bad).process(_ctx(ctx), _asset())
    assert result.status is not ImageResultStatus.RESOLVED_INTERNAL
    rejections = (result.evidence or {}).get("supplier_label_rejections") or []
    assert any(
        r.get("validation_status") == LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value
        for r in rejections
    )


def test_regex_nested_quantifiers_rejected() -> None:
    for pattern in ("(a+)+$", "(a*)*$", "(a|aa)+$"):
        with pytest.raises(LabelProfileConfigurationError):
            compile_payload_pattern(pattern)
    # Safe pattern still compiles.
    compile_payload_pattern(r"^ABC[0-9]+$")


def test_legacy_job_without_label_profiles() -> None:
    result = _strategy("PLAIN-SKU|2").process(
        _ctx(LabelValidationContext(resolved_profiles=None)),
        _asset(),
    )
    assert result.status in (
        ImageResultStatus.RESOLVED_INTERNAL,
        ImageResultStatus.PENDING_MANUAL_REVIEW,
        ImageResultStatus.UNRECOGNIZED,
    )


def test_image_processing_context_validation_context_is_typed() -> None:
    annotations = ImageProcessingContext.__annotations__
    assert "label_validation_context" in annotations
    assert "Any" not in str(annotations["label_validation_context"])
