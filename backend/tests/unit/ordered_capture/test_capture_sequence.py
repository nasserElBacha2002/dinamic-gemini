"""Unit tests — Phase 1 capture sequence helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.capture_sequence import (
    position_order_for_asset,
    sort_assets_by_logical_sequence,
    validate_complete_sequence,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType


def _asset(
    *,
    id: str,
    seq: int | None,
    uploaded_offset: int,
    client_file_id: str | None = None,
) -> SourceAsset:
    return SourceAsset(
        id=id,
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{id}.jpg",
        storage_path=f"/tmp/{id}.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc).replace(
            second=uploaded_offset
        ),
        upload_client_file_id=client_file_id or f"client-{id}",
        ordered_capture_session_id="sess-1" if seq is not None else None,
        sequence_number=seq,
        sequence_source="CLIENT_ASSIGNED" if seq is not None else None,
    )


def test_out_of_order_uploads_sort_by_sequence_number() -> None:
    # Arrival order: 6,2,5,1,7,4,3
    arrival = [6, 2, 5, 1, 7, 4, 3]
    assets = [
        _asset(id=f"a{n}", seq=n, uploaded_offset=i) for i, n in enumerate(arrival)
    ]
    ordered = sort_assets_by_logical_sequence(assets)
    assert [a.sequence_number for a in ordered] == [1, 2, 3, 4, 5, 6, 7]


def test_validate_complete_sequence_ok() -> None:
    assets = [_asset(id=f"a{n}", seq=n, uploaded_offset=n) for n in range(1, 8)]
    assert validate_complete_sequence(assets, expected_count=7) == []


def test_validate_complete_sequence_missing() -> None:
    assets = [_asset(id=f"a{n}", seq=n, uploaded_offset=n) for n in (1, 2, 3, 4, 5, 7)]
    errors = validate_complete_sequence(assets, expected_count=7)
    assert errors


def test_validate_complete_sequence_duplicate() -> None:
    assets = [
        _asset(id="a1", seq=1, uploaded_offset=1),
        _asset(id="a2", seq=2, uploaded_offset=2),
        _asset(id="a3", seq=2, uploaded_offset=3, client_file_id="other"),
    ]
    errors = validate_complete_sequence(assets, expected_count=3)
    assert any("duplicate" in e for e in errors)


def test_position_order_alias_equals_sequence() -> None:
    asset = _asset(id="a1", seq=4, uploaded_offset=0)
    assert position_order_for_asset(asset, fallback_index=0) == 4
    legacy = _asset(id="L", seq=None, uploaded_offset=0)
    assert position_order_for_asset(legacy, fallback_index=2) == 2
