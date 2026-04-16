"""Route-level tests for GET .../assets/{asset_id}/image-display-url."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.dependencies import (
    get_artifact_storage,
    get_list_aisle_assets_use_case,
    get_result_context_resolver,
)
from src.api.schemas.asset_schemas import SourceAssetImageDisplayUrlResponse
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.aisle.entities import Aisle, AisleStatus
from src.application.services.result_context_resolver import ResultContextResolver
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class StubListAisleAssetsUseCase:
    """Returns a fixed list of assets (inventory/aisle ids ignored)."""

    def __init__(self, assets: Sequence[SourceAsset], *, aisle: Aisle | None = None) -> None:
        self._assets = list(assets)
        self._aisle = aisle

    def execute(self, inventory_id: str, aisle_id: str) -> Sequence[SourceAsset]:
        return self._assets

    def get_validated_aisle(self, inventory_id: str, aisle_id: str) -> Aisle:
        from src.application.errors import AisleNotFoundError

        if self._aisle is None:
            raise AisleNotFoundError("stub: aisle not configured")
        if self._aisle.id != aisle_id or self._aisle.inventory_id != inventory_id:
            raise AisleNotFoundError("stub: aisle mismatch")
        return self._aisle


class StubS3ArtifactStorage:
    bucket = "bucket-x"

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        return f"https://signed.example/{key}?ttl={expires_in_sec}"


@pytest.fixture
def admin_auth():
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    yield
    app.dependency_overrides.pop(get_current_admin, None)


def _register_aisle_resolver(inv_id: str, aisle_id: str) -> Aisle:
    """ResultContextResolver wiring; returns aisle for HEIC stubs (Phase 5: no route repo)."""
    now = datetime.now(timezone.utc)
    aisle_obj = Aisle(
        id=aisle_id,
        inventory_id=inv_id,
        code="T",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
        operational_job_id=None,
    )
    ar = MemoryAisleRepository()
    ar.save(aisle_obj)
    app.dependency_overrides[get_result_context_resolver] = lambda: ResultContextResolver(
        MemoryJobRepository(), MemoryPositionRepository()
    )
    return aisle_obj


def _patch_display_settings(monkeypatch: pytest.MonkeyPatch, output_dir: Path) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "output_dir": str(output_dir),
            "artifact_storage_legacy_local_read_enabled": True,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    monkeypatch.setattr("src.api.routes.v3.assets.load_settings", lambda: fake_settings)
    monkeypatch.setattr("src.api.services.v3_stored_artifact_access.load_settings", lambda: fake_settings)


def test_image_display_url_s3_returns_presigned_strategy(admin_auth, monkeypatch, tmp_path: Path) -> None:
    inv_id, aisle_id, asset_id = "inv-s3", "aisle-s3", "asset-s3-1"
    now = datetime.now(timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="legacy/ignored",
        mime_type="image/jpeg",
        uploaded_at=now,
        storage_provider="s3",
        storage_bucket="bucket-x",
        storage_key="logical/k1.jpg",
    )
    _patch_display_settings(monkeypatch, tmp_path)
    aisle_obj = _register_aisle_resolver(inv_id, aisle_id)
    app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: StubListAisleAssetsUseCase(
        [asset], aisle=aisle_obj
    )
    app.dependency_overrides[get_artifact_storage] = lambda: StubS3ArtifactStorage()
    try:
        r = TestClient(app).get(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["display_strategy"] == "presigned_url"
        assert data["requires_authenticated_fetch"] is False
        assert data["image_url"] == "https://signed.example/logical/k1.jpg?ttl=900"
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)
        app.dependency_overrides.pop(get_artifact_storage, None)


def test_image_display_url_local_returns_authenticated_fetch_strategy(admin_auth, monkeypatch, tmp_path: Path) -> None:
    inv_id, aisle_id, asset_id = "inv-loc", "aisle-loc", "asset-loc-1"
    now = datetime.now(timezone.utc)
    (tmp_path / "v3_uploads" / "keys").mkdir(parents=True, exist_ok=True)
    (tmp_path / "v3_uploads" / "keys" / "photo.jpg").write_bytes(b"jpeg")

    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="",
        mime_type="image/jpeg",
        uploaded_at=now,
        storage_provider="local",
        storage_bucket=None,
        storage_key="keys/photo.jpg",
    )
    _patch_display_settings(monkeypatch, tmp_path)
    aisle_obj = _register_aisle_resolver(inv_id, aisle_id)
    app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: StubListAisleAssetsUseCase(
        [asset], aisle=aisle_obj
    )
    art_root = tmp_path / "_artifact_stub"
    art_root.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_artifact_storage] = lambda: V3ArtifactStorageAdapter(art_root)
    try:
        r = TestClient(app).get(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["display_strategy"] == "authenticated_file_fetch"
        assert data["requires_authenticated_fetch"] is True
        assert data["image_url"] is None
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)
        app.dependency_overrides.pop(get_artifact_storage, None)


def test_image_display_url_legacy_row_returns_authenticated_fetch_when_file_exists(
    admin_auth, monkeypatch, tmp_path: Path
) -> None:
    inv_id, aisle_id = "inv-leg", "aisle-leg"
    asset_id = "asset-leg-1"
    rel = f"{inv_id}/{aisle_id}/{asset_id}.jpg"
    file_path = tmp_path / "v3_uploads" / rel
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x")
    now = datetime.now(timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path=rel,
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    _patch_display_settings(monkeypatch, tmp_path)
    aisle_obj = _register_aisle_resolver(inv_id, aisle_id)
    app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: StubListAisleAssetsUseCase(
        [asset], aisle=aisle_obj
    )
    art_root = tmp_path / "_artifact_stub2"
    art_root.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_artifact_storage] = lambda: V3ArtifactStorageAdapter(art_root)
    try:
        r = TestClient(app).get(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["display_strategy"] == "authenticated_file_fetch"
        assert data["requires_authenticated_fetch"] is True
        assert data["image_url"] is None
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)
        app.dependency_overrides.pop(get_artifact_storage, None)


def test_image_display_url_local_missing_file_returns_404(admin_auth, monkeypatch, tmp_path: Path) -> None:
    inv_id, aisle_id, asset_id = "inv-bad", "aisle-bad", "asset-bad-1"
    now = datetime.now(timezone.utc)
    (tmp_path / "v3_uploads").mkdir(parents=True, exist_ok=True)

    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="",
        mime_type="image/jpeg",
        uploaded_at=now,
        storage_provider="local",
        storage_bucket=None,
        storage_key="nope.jpg",
    )
    _patch_display_settings(monkeypatch, tmp_path)
    aisle_obj = _register_aisle_resolver(inv_id, aisle_id)
    app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: StubListAisleAssetsUseCase(
        [asset], aisle=aisle_obj
    )
    art_root = tmp_path / "_artifact_stub3"
    art_root.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_artifact_storage] = lambda: V3ArtifactStorageAdapter(art_root)
    try:
        r = TestClient(app).get(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url"
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)
        app.dependency_overrides.pop(get_artifact_storage, None)


def test_source_asset_image_display_response_model_rejects_inconsistent_strategy() -> None:
    with pytest.raises(ValidationError):
        SourceAssetImageDisplayUrlResponse(
            image_url="https://x.example/a",
            requires_authenticated_fetch=True,
            display_strategy="presigned_url",
        )
    with pytest.raises(ValidationError):
        SourceAssetImageDisplayUrlResponse(
            image_url=None,
            requires_authenticated_fetch=False,
            display_strategy="authenticated_file_fetch",
        )
