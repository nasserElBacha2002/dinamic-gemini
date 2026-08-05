"""Operational role of a job photo for image-coverage / uncounted queues.

Reuses ``reduce_asset_detections`` — does not duplicate detection-status lists.
Filename is never consulted.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.application.services.positioning_operational.sequence_event_classifier import (
    PositionSequenceEventKind,
    reduce_asset_detections,
)
from src.domain.position_label_detection.entities import ImagePositionLabelDetection


class AssetOperationalRole(str, Enum):
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    PRODUCT_WITHOUT_RESULT = "PRODUCT_WITHOUT_RESULT"
    POSITION_LABEL_RESOLVED = "POSITION_LABEL_RESOLVED"
    POSITION_LABEL_UNRESOLVED = "POSITION_LABEL_UNRESOLVED"
    NO_POSITION_SYMBOL = "NO_POSITION_SYMBOL"
    UNKNOWN = "UNKNOWN"


class UncountedExclusionReason(str, Enum):
    HAS_PRODUCT_RESULT = "HAS_PRODUCT_RESULT"
    POSITION_LABEL_RESOLVED = "POSITION_LABEL_RESOLVED"
    POSITION_LABEL_UNRESOLVED = "POSITION_LABEL_UNRESOLVED"
    POSITION_TRANSITION_APPLIED = "POSITION_TRANSITION_APPLIED"
    NONE = "NONE"


_POSITIONING_EVENT_KINDS = frozenset(
    {
        PositionSequenceEventKind.POSITION_LABEL_RESOLVED,
        PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED,
        PositionSequenceEventKind.POSITION_TRANSITION_APPLIED,
    }
)


@dataclass(frozen=True)
class AssetUncountedClassification:
    operational_role: AssetOperationalRole
    is_product_candidate: bool
    excluded_from_uncounted: bool
    uncounted_reason: UncountedExclusionReason


def classify_asset_for_uncounted(
    detections: Sequence[ImagePositionLabelDetection],
    *,
    has_product_result: bool,
) -> AssetUncountedClassification:
    """Classify one asset for the unmatched-images queue.

    Position-label events (resolved or unresolved) are never product-uncounted
    candidates. ``NO_LABEL`` / ``FEATURE_DISABLED`` remain product candidates when
    there is no product result.
    """
    if has_product_result:
        return AssetUncountedClassification(
            operational_role=AssetOperationalRole.PRODUCT_IMAGE,
            is_product_candidate=False,
            excluded_from_uncounted=True,
            uncounted_reason=UncountedExclusionReason.HAS_PRODUCT_RESULT,
        )

    event = reduce_asset_detections(detections)
    kind = event.event_kind

    if kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED:
        return AssetUncountedClassification(
            operational_role=AssetOperationalRole.POSITION_LABEL_RESOLVED,
            is_product_candidate=False,
            excluded_from_uncounted=True,
            uncounted_reason=UncountedExclusionReason.POSITION_LABEL_RESOLVED,
        )
    if kind is PositionSequenceEventKind.POSITION_TRANSITION_APPLIED:
        return AssetUncountedClassification(
            operational_role=AssetOperationalRole.POSITION_LABEL_RESOLVED,
            is_product_candidate=False,
            excluded_from_uncounted=True,
            uncounted_reason=UncountedExclusionReason.POSITION_TRANSITION_APPLIED,
        )
    if kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED:
        return AssetUncountedClassification(
            operational_role=AssetOperationalRole.POSITION_LABEL_UNRESOLVED,
            is_product_candidate=False,
            excluded_from_uncounted=True,
            uncounted_reason=UncountedExclusionReason.POSITION_LABEL_UNRESOLVED,
        )
    if kind is PositionSequenceEventKind.NO_POSITION_SYMBOL:
        return AssetUncountedClassification(
            operational_role=AssetOperationalRole.NO_POSITION_SYMBOL,
            is_product_candidate=True,
            excluded_from_uncounted=False,
            uncounted_reason=UncountedExclusionReason.NONE,
        )
    return AssetUncountedClassification(
        operational_role=AssetOperationalRole.UNKNOWN,
        is_product_candidate=True,
        excluded_from_uncounted=False,
        uncounted_reason=UncountedExclusionReason.NONE,
    )


def source_asset_ids_excluded_as_position_labels(
    detections: Sequence[ImagePositionLabelDetection],
) -> frozenset[str]:
    """Assets whose effective role is a positioning label (any explicit event)."""
    by_asset: dict[str, list[ImagePositionLabelDetection]] = defaultdict(list)
    for det in detections:
        asset_id = (det.source_asset_id or "").strip()
        if asset_id:
            by_asset[asset_id].append(det)

    excluded: set[str] = set()
    for asset_id, rows in by_asset.items():
        event = reduce_asset_detections(rows)
        if event.event_kind in _POSITIONING_EVENT_KINDS:
            excluded.add(asset_id)
    return frozenset(excluded)
