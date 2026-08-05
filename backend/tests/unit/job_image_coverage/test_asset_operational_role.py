"""Unit tests: position-label assets are excluded from uncounted image queues."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.job_image_coverage.asset_operational_role import (
    AssetOperationalRole,
    UncountedExclusionReason,
    classify_asset_for_uncounted,
    source_asset_ids_excluded_as_position_labels,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _det(
    *,
    det_id: str = "d1",
    asset_id: str = "asset-1",
    status: PositionLabelDetectionStatus = PositionLabelDetectionStatus.VALID,
    label_id: str | None = "L1",
    name: str | None = "A",
) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=det_id,
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        source_asset_id=asset_id,
        detection_status=status,
        signature_status=PositionLabelSignatureStatus.VALID,
        payload_version=1,
        raw_payload_hash=None,
        detector_name="code_scan_shared",
        detector_version="1",
        created_at=NOW,
        updated_at=NOW,
        position_label_id=label_id,
        position_name_snapshot=name,
    )


def test_valid_without_product_excluded() -> None:
    c = classify_asset_for_uncounted([_det(status=PositionLabelDetectionStatus.VALID)], has_product_result=False)
    assert c.excluded_from_uncounted is True
    assert c.is_product_candidate is False
    assert c.operational_role is AssetOperationalRole.POSITION_LABEL_RESOLVED


def test_legacy_without_product_excluded() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is True
    assert c.operational_role is AssetOperationalRole.POSITION_LABEL_RESOLVED


def test_label_not_found_excluded_as_unresolved() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.LABEL_NOT_FOUND, label_id=None)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is True
    assert c.operational_role is AssetOperationalRole.POSITION_LABEL_UNRESOLVED
    assert c.uncounted_reason is UncountedExclusionReason.POSITION_LABEL_UNRESOLVED


def test_invalid_signature_excluded() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.INVALID_SIGNATURE, label_id=None)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is True


def test_ambiguous_excluded() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION, label_id=None)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is True
    assert c.is_product_candidate is False


def test_no_label_included_as_product_candidate() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.NO_LABEL, label_id=None)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is False
    assert c.is_product_candidate is True
    assert c.operational_role is AssetOperationalRole.NO_POSITION_SYMBOL


def test_no_detection_included() -> None:
    c = classify_asset_for_uncounted([], has_product_result=False)
    assert c.excluded_from_uncounted is False
    assert c.is_product_candidate is True


def test_with_product_excluded_regardless_of_detection() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.VALID)],
        has_product_result=True,
    )
    assert c.excluded_from_uncounted is True
    assert c.operational_role is AssetOperationalRole.PRODUCT_IMAGE


def test_filename_irrelevant_position_name_excluded_by_domain() -> None:
    c = classify_asset_for_uncounted(
        [_det(name="pasillo01.jpg", label_id="L1")],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is True


def test_pasillo_filename_without_detection_not_excluded() -> None:
    # Filename is never consulted — empty detections stay product candidates.
    c = classify_asset_for_uncounted([], has_product_result=False)
    assert c.excluded_from_uncounted is False


def test_multi_detection_order_independent_exclusion() -> None:
    rows = [
        _det(det_id="n", status=PositionLabelDetectionStatus.NO_LABEL, label_id=None),
        _det(det_id="v", status=PositionLabelDetectionStatus.VALID, label_id="L1"),
    ]
    a = classify_asset_for_uncounted(rows, has_product_result=False)
    b = classify_asset_for_uncounted(list(reversed(rows)), has_product_result=False)
    assert a == b
    assert a.excluded_from_uncounted is True


def test_feature_disabled_is_product_candidate() -> None:
    c = classify_asset_for_uncounted(
        [_det(status=PositionLabelDetectionStatus.FEATURE_DISABLED, label_id=None)],
        has_product_result=False,
    )
    assert c.excluded_from_uncounted is False
    assert c.is_product_candidate is True
    assert c.operational_role is AssetOperationalRole.NO_POSITION_SYMBOL


def test_excluded_asset_id_set() -> None:
    detections = [
        _det(det_id="1", asset_id="pos-a", status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW),
        _det(det_id="2", asset_id="prod-b", status=PositionLabelDetectionStatus.NO_LABEL, label_id=None),
        _det(det_id="3", asset_id="pos-c", status=PositionLabelDetectionStatus.LABEL_NOT_FOUND, label_id=None),
    ]
    excluded = source_asset_ids_excluded_as_position_labels(detections)
    assert excluded == frozenset({"pos-a", "pos-c"})
