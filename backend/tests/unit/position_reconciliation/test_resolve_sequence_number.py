"""Unit tests for sequence resolution used when building OrderedImageFrame."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    ReconcileJobPositionsUseCase,
)


@dataclass
class _Asset:
    sequence_number: int | None = None


def _link(*, sequence_number: int | None = None, position_order: int = 0) -> JobSourceAssetLink:
    return JobSourceAssetLink(
        id="link-1",
        job_id="job-1",
        source_asset_id="asset-1",
        asset_role="primary",
        position_order=position_order,
        checksum=None,
        storage_key=None,
        mime_type=None,
        size_bytes=None,
        width=None,
        height=None,
        stage=None,
        provider_request_id=None,
        created_at=datetime.now(timezone.utc),
        sequence_number=sequence_number,
    )


def test_prefers_asset_sequence_number():
    assert ReconcileJobPositionsUseCase._resolve_sequence_number(
        asset=_Asset(sequence_number=7),
        link=_link(sequence_number=3, position_order=1),
    ) == (7, "capture")


def test_falls_back_to_link_sequence_number():
    assert ReconcileJobPositionsUseCase._resolve_sequence_number(
        asset=_Asset(sequence_number=None),
        link=_link(sequence_number=4, position_order=1),
    ) == (4, "link")


def test_falls_back_to_position_order_for_system_uploads():
    assert ReconcileJobPositionsUseCase._resolve_sequence_number(
        asset=_Asset(sequence_number=None),
        link=_link(sequence_number=None, position_order=0),
    ) == (0, "position_order")
    assert ReconcileJobPositionsUseCase._resolve_sequence_number(
        asset=None,
        link=_link(sequence_number=None, position_order=5),
    ) == (5, "position_order")


def test_system_upload_reorders_position_photo_before_item():
    from src.domain.position_reconciliation.entities import (
        ItemResultRef,
        OrderedImageFrame,
        PositionDetectionRef,
    )

    item_first = OrderedImageFrame(
        source_asset_id="item",
        ordered_capture_session_id=None,
        sequence_number=0,
        item_results=(ItemResultRef(result_id="r1"),),
    )
    position_second = OrderedImageFrame(
        source_asset_id="position",
        ordered_capture_session_id=None,
        sequence_number=1,
        position_detections=(
            PositionDetectionRef(
                id="d1",
                client_id="c1",
                detection_status="LEGACY_UNSIGNED_REQUIRES_REVIEW",
                signature_status="MISSING",
                position_label_id="label-1",
            ),
        ),
    )
    out = ReconcileJobPositionsUseCase._normalize_system_upload_frame_order(
        [item_first, position_second],
        ["position_order", "position_order"],
    )
    assert [f.source_asset_id for f in out] == ["position", "item"]
    assert [f.sequence_number for f in out] == [0, 1]


def test_system_upload_preserves_interleaved_position_walk():
    """pos1 → items → pos2 → items must NOT collapse to all positions first.

    Regression: old normalize put every position photo before every item, so forward-fill
    assigned the last position (02) to products that belonged to 01.
    """
    from src.domain.position_reconciliation.entities import (
        ItemResultRef,
        OrderedImageFrame,
        PositionDetectionRef,
    )

    def _pos(asset_id: str, seq: int, label: str) -> OrderedImageFrame:
        return OrderedImageFrame(
            source_asset_id=asset_id,
            ordered_capture_session_id=None,
            sequence_number=seq,
            position_detections=(
                PositionDetectionRef(
                    id=f"d-{asset_id}",
                    client_id="c1",
                    detection_status="LEGACY_UNSIGNED_REQUIRES_REVIEW",
                    signature_status="MISSING",
                    position_label_id=label,
                ),
            ),
        )

    def _item(asset_id: str, seq: int) -> OrderedImageFrame:
        return OrderedImageFrame(
            source_asset_id=asset_id,
            ordered_capture_session_id=None,
            sequence_number=seq,
            item_results=(ItemResultRef(result_id=f"r-{asset_id}"),),
        )

    frames = [
        _pos("pasillo01", 0, "label-01"),
        _item("item-a", 1),
        _item("item-b", 2),
        _pos("pasillo02", 3, "label-02"),
        _item("item-c", 4),
        _item("item-d", 5),
    ]
    sources = ["position_order"] * len(frames)
    out = ReconcileJobPositionsUseCase._normalize_system_upload_frame_order(frames, sources)
    assert [f.source_asset_id for f in out] == [
        "pasillo01",
        "item-a",
        "item-b",
        "pasillo02",
        "item-c",
        "item-d",
    ]
    assert [f.sequence_number for f in out] == list(range(6))


def test_system_upload_lifts_only_first_position_when_items_lead():
    """Leading items before the first position lift that position only; later walk stays."""
    from src.domain.position_reconciliation.entities import (
        ItemResultRef,
        OrderedImageFrame,
        PositionDetectionRef,
    )

    def _pos(asset_id: str, seq: int, label: str) -> OrderedImageFrame:
        return OrderedImageFrame(
            source_asset_id=asset_id,
            ordered_capture_session_id=None,
            sequence_number=seq,
            position_detections=(
                PositionDetectionRef(
                    id=f"d-{asset_id}",
                    client_id="c1",
                    detection_status="VALID",
                    signature_status="VALID",
                    position_label_id=label,
                ),
            ),
        )

    def _item(asset_id: str, seq: int) -> OrderedImageFrame:
        return OrderedImageFrame(
            source_asset_id=asset_id,
            ordered_capture_session_id=None,
            sequence_number=seq,
            item_results=(ItemResultRef(result_id=f"r-{asset_id}"),),
        )

    frames = [
        _item("lead-1", 0),
        _item("lead-2", 1),
        _pos("pasillo01", 2, "label-01"),
        _item("mid", 3),
        _pos("pasillo02", 4, "label-02"),
        _item("tail", 5),
    ]
    out = ReconcileJobPositionsUseCase._normalize_system_upload_frame_order(
        frames,
        ["position_order"] * len(frames),
    )
    assert [f.source_asset_id for f in out] == [
        "pasillo01",
        "lead-1",
        "lead-2",
        "mid",
        "pasillo02",
        "tail",
    ]


def test_capture_sequence_is_not_reordered():
    from src.domain.position_reconciliation.entities import (
        ItemResultRef,
        OrderedImageFrame,
        PositionDetectionRef,
    )

    item_first = OrderedImageFrame(
        source_asset_id="item",
        ordered_capture_session_id="s1",
        sequence_number=1,
        item_results=(ItemResultRef(result_id="r1"),),
    )
    position_second = OrderedImageFrame(
        source_asset_id="position",
        ordered_capture_session_id="s1",
        sequence_number=2,
        position_detections=(
            PositionDetectionRef(
                id="d1",
                client_id="c1",
                detection_status="VALID",
                signature_status="VALID",
                position_label_id="label-1",
            ),
        ),
    )
    out = ReconcileJobPositionsUseCase._normalize_system_upload_frame_order(
        [item_first, position_second],
        ["capture", "capture"],
    )
    assert [f.source_asset_id for f in out] == ["item", "position"]
