"""
Tests for MemorySourceAssetRepository — ordering matches SQL (uploaded_at ASC).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


def test_list_by_aisle_returns_assets_ordered_by_uploaded_at_asc() -> None:
    """list_by_aisle returns assets in uploaded_at ASC order to match SqlSourceAssetRepository."""
    repo = MemorySourceAssetRepository()
    t1 = datetime(2025, 3, 6, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2025, 3, 6, 9, 0, 0, tzinfo=timezone.utc)
    repo.save(
        SourceAsset(
            "a2", "aisle-1", SourceAssetType.PHOTO, "b.jpg", "/p/b.jpg", "image/jpeg", t2
        )
    )
    repo.save(
        SourceAsset(
            "a1", "aisle-1", SourceAssetType.PHOTO, "a.jpg", "/p/a.jpg", "image/jpeg", t1
        )
    )
    repo.save(
        SourceAsset(
            "a3", "aisle-1", SourceAssetType.VIDEO, "c.mp4", "/p/c.mp4", "video/mp4", t3
        )
    )
    result = repo.list_by_aisle("aisle-1")
    assert [a.id for a in result] == ["a3", "a1", "a2"]  # t3=09, t1=10, t2=11
    assert [a.uploaded_at for a in result] == [t3, t1, t2]
