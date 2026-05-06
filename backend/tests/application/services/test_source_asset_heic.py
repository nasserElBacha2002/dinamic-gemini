"""Tests for :mod:`src.application.services.source_asset_heic`."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.source_asset_heic import (
    select_source_asset_by_id,
    source_asset_is_heic,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType

_now = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _asset(
    *,
    asset_id: str = "a1",
    mime: str = "image/jpeg",
    storage: str = "p/x.jpg",
    orig: str = "x.jpg",
) -> SourceAsset:
    return SourceAsset(
        id=asset_id,
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename=orig,
        storage_path=storage,
        mime_type=mime,
        uploaded_at=_now,
    )


def test_select_source_asset_by_id() -> None:
    a1 = _asset(asset_id="x")
    a2 = _asset(asset_id="y")
    assert select_source_asset_by_id([a1, a2], "y") is a2
    assert select_source_asset_by_id([a1, a2], "z") is None


def test_source_asset_is_heic_mime() -> None:
    assert source_asset_is_heic(_asset(mime="image/heic")) is True
    assert source_asset_is_heic(_asset(mime="IMAGE/HEIF")) is True


def test_source_asset_is_heic_suffix() -> None:
    assert source_asset_is_heic(_asset(mime="image/jpeg", orig="a.heic", storage="b")) is True
    assert (
        source_asset_is_heic(_asset(mime="image/jpeg", orig="a.jpg", storage="in/b.heif")) is True
    )


def test_source_asset_is_heic_false() -> None:
    assert source_asset_is_heic(_asset(mime="image/jpeg", orig="a.jpg", storage="b.png")) is False
