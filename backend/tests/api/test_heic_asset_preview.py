"""
HEIC/HEIF evidence preview — backend asset file endpoint serves normalized JPG when available.

Tests:
- HEIC asset with normalized JPG in **resolved result-context job** → 200 and JPG content
- HEIC asset with no normalized JPG → 404 and clear message
- JPG asset → 200 and original file (unchanged)
- Path traversal in stored_normalized_filename → rejected, 404 (path-safety)
- Manifest has entry but normalized file missing on disk → 404
- job_id query param: explicit job overrides operational pointer for preview → 200
- No “latest job” fallback when explicit or resolved job lacks normalized artifact → 404
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_artifact_storage,
    get_list_aisle_assets_use_case,
    get_result_context_resolver,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.pipeline.v3_job_executor import RUN_ID


class StubListAisleAssetsUseCase:
    """Returns a fixed list of assets for testing."""

    def __init__(self, assets: Sequence[SourceAsset]) -> None:
        self._assets = list(assets)

    def execute(self, inventory_id: str, aisle_id: str) -> Sequence[SourceAsset]:
        return self._assets


@contextmanager
def _patch_local_asset_settings(output_dir: Path):
    """Patch settings for asset file route + Phase 4 stored-artifact service (same output_dir, legacy on)."""
    s = type(
        "Settings",
        (),
        {
            "output_dir": str(output_dir),
            "artifact_storage_legacy_local_read_enabled": True,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    with patch("src.api.routes.v3.assets.load_settings", return_value=s), patch(
        "src.api.services.v3_stored_artifact_access.load_settings", return_value=s
    ):
        yield


def _register_aisle_and_resolver(
    inv_id: str,
    aisle_id: str,
    *,
    operational_job_id: str | None,
) -> None:
    """Match GET asset routes: aisle row + ResultContextResolver (operational / legacy / explicit query)."""
    now = datetime.now(timezone.utc)
    ar = MemoryAisleRepository()
    ar.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code="T",
            status=AisleStatus.PROCESSED,
            created_at=now,
            updated_at=now,
            operational_job_id=operational_job_id,
        )
    )
    app.dependency_overrides[get_aisle_repo] = lambda: ar
    app.dependency_overrides[get_result_context_resolver] = lambda: ResultContextResolver(
        MemoryJobRepository(), MemoryPositionRepository()
    )


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def _phase4_api_dependency_stubs(output_dir: Path) -> None:
    """Router requires admin auth and artifact storage for asset file endpoint (Phase 4)."""
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    stub_root = output_dir / "_artifact_store_stub"
    stub_root.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_artifact_storage] = lambda: V3ArtifactStorageAdapter(stub_root)
    yield
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_artifact_storage, None)


def test_heic_asset_file_serves_normalized_jpg_when_available(output_dir: Path) -> None:
    """When asset is HEIC and operational job has normalized JPG for that asset, endpoint returns JPG."""
    inv_id, aisle_id, asset_id = "inv-heic", "aisle-heic", "asset-heic-1"
    job_id = "job-heic-xyz"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"
    normalized_name = "0001_photo.jpg"
    jpeg_content = b"fake-jpeg-preview-content"

    # On-disk: v3_uploads asset file (HEIC), job manifest + normalized JPG
    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic-placeholder")

    job_dir = output_dir / job_id
    run_dir = job_dir / RUN_ID
    (run_dir / "input_photos_normalized").mkdir(parents=True, exist_ok=True)
    (run_dir / "input_photos_normalized" / normalized_name).write_bytes(jpeg_content)

    manifest = {
        "input_type": "photos",
        "photos": [
            {"image_id": asset_id, "stored_filename": "0001_x.heic", "stored_normalized_filename": normalized_name},
        ],
    }
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="IMG_2381.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=job_id)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 200
            assert resp.content == jpeg_content
            assert resp.headers.get("content-type", "").startswith("image/jpeg")
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)


def test_heic_asset_file_returns_404_when_no_normalized_preview(output_dir: Path) -> None:
    """When asset is HEIC but no normalized JPG exists, return 404 with clear message."""
    inv_id, aisle_id, asset_id = "inv-heic", "aisle-heic", "asset-heic-2"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic-placeholder")

    # No job / no manifest / no normalized file
    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="IMG.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=None)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 404
            assert resp.json().get("detail") == "Preview is not available for this image"
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)


def test_jpg_asset_file_serves_original_unchanged(output_dir: Path) -> None:
    """JPG/PNG assets are served as before (original file)."""
    inv_id, aisle_id, asset_id = "inv-jpg", "aisle-jpg", "asset-jpg-1"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.jpg"
    original_content = b"original-jpeg-bytes"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(original_content)

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="photo.jpg",
        storage_path=storage_path,
        mime_type="image/jpeg",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 200
            assert resp.content == original_content
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)


def test_asset_file_returns_404_file_not_found_when_missing_on_disk(output_dir: Path) -> None:
    """When asset exists in list but the file is missing on disk, return 404 with 'Asset file not found'."""
    inv_id, aisle_id, asset_id = "inv-miss", "aisle-miss", "asset-miss-1"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.jpg"
    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    # Do NOT write (base / storage_path) so file_path.is_file() is False

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="photo.jpg",
        storage_path=storage_path,
        mime_type="image/jpeg",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 404
            assert "not found" in resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)


def test_heic_asset_file_rejects_path_traversal_in_manifest(output_dir: Path) -> None:
    """Malicious or corrupt stored_normalized_filename (path traversal) must not be served; return 404."""
    inv_id, aisle_id, asset_id = "inv-safe", "aisle-safe", "asset-safe-1"
    job_id = "job-safe-xyz"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic")

    # Manifest claims a path that would escape the normalized dir
    manifest = {
        "input_type": "photos",
        "photos": [
            {
                "image_id": asset_id,
                "stored_filename": "0001_x.heic",
                "stored_normalized_filename": "../../../v3_uploads/escape.jpg",
            },
        ],
    }
    job_dir = output_dir / job_id
    (job_dir / RUN_ID).mkdir(parents=True, exist_ok=True)
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=job_id)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 404
            assert "preview" in (resp.json().get("detail") or "").lower() or "not available" in (resp.json().get("detail") or "").lower()
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)


def test_heic_asset_file_404_when_manifest_entry_exists_but_file_missing(output_dir: Path) -> None:
    """When manifest has stored_normalized_filename for the asset but the file is missing on disk, return 404."""
    inv_id, aisle_id, asset_id = "inv-miss", "aisle-miss", "asset-miss-1"
    job_id = "job-miss-xyz"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"
    normalized_name = "0001_missing.jpg"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic")

    job_dir = output_dir / job_id
    run_dir = job_dir / RUN_ID
    (run_dir / "input_photos_normalized").mkdir(parents=True, exist_ok=True)
    # Do NOT create run_dir/input_photos_normalized/0001_missing.jpg

    manifest = {
        "input_type": "photos",
        "photos": [
            {"image_id": asset_id, "stored_filename": "0001_x.heic", "stored_normalized_filename": normalized_name},
        ],
    }
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=job_id)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp.status_code == 404
            assert resp.json().get("detail") == "Preview is not available for this image"
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)


def test_heic_asset_file_job_id_param_uses_specified_job_when_latest_differs(output_dir: Path) -> None:
    """Operational pointer may differ from the run that holds the asset; explicit job_id selects the folder."""
    inv_id, aisle_id, asset_id = "inv-multi", "aisle-multi", "asset-multi-1"
    job_a = "job-position-run"
    job_b = "job-latest-run"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"
    normalized_name = "0001_photo.jpg"
    jpeg_content = b"normalized-from-job-a"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic-placeholder")

    # Job A (position's job): has normalized file for this asset
    job_a_dir = output_dir / job_a
    run_a = job_a_dir / RUN_ID
    (run_a / "input_photos_normalized").mkdir(parents=True, exist_ok=True)
    (run_a / "input_photos_normalized" / normalized_name).write_bytes(jpeg_content)
    manifest_a = {
        "input_type": "photos",
        "photos": [
            {"image_id": asset_id, "stored_filename": "0001_x.heic", "stored_normalized_filename": normalized_name},
        ],
    }
    (job_a_dir / "input_manifest.json").write_text(json.dumps(manifest_a), encoding="utf-8")

    # Job B (latest): does not have this asset in manifest (e.g. different run, different photos)
    job_b_dir = output_dir / job_b
    (job_b_dir / RUN_ID).mkdir(parents=True, exist_ok=True)
    manifest_b = {"input_type": "photos", "photos": []}
    (job_b_dir / "input_manifest.json").write_text(json.dumps(manifest_b), encoding="utf-8")

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="IMG_2380.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=job_b)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp_no_job = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file"
            )
            assert resp_no_job.status_code == 404, "operational job_B has no normalized asset -> 404"

            resp_with_job = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file",
                params={"job_id": job_a},
            )
            assert resp_with_job.status_code == 200
            assert resp_with_job.content == jpeg_content
            assert resp_with_job.headers.get("content-type", "").startswith("image/jpeg")
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)


def test_heic_asset_file_no_fallback_when_explicit_job_has_no_normalized_file(output_dir: Path) -> None:
    """Explicit job_id resolves only that run's folder — no silent cross-run fallback."""
    inv_id, aisle_id, asset_id = "inv-fb", "aisle-fb", "asset-fb-1"
    job_bad = "job-old-no-normalized"
    job_other = "job-latest-has-normalized"
    storage_path = f"{inv_id}/{aisle_id}/{asset_id}.heic"
    normalized_name = "0001_photo.jpg"
    jpeg_content = b"normalized-from-other"

    base = output_dir / "v3_uploads"
    (base / inv_id / aisle_id).mkdir(parents=True, exist_ok=True)
    (base / storage_path).write_bytes(b"heic-placeholder")

    job_bad_dir = output_dir / job_bad
    run_old = job_bad_dir / RUN_ID
    run_old.mkdir(parents=True, exist_ok=True)
    (run_old / "input_photos_normalized").mkdir(parents=True, exist_ok=True)
    manifest_old = {
        "input_type": "photos",
        "photos": [
            {"image_id": asset_id, "stored_filename": "0001_x.heic", "stored_normalized_filename": "0001_missing.jpg"},
        ],
    }
    (job_bad_dir / "input_manifest.json").write_text(json.dumps(manifest_old), encoding="utf-8")

    job_lat_dir = output_dir / job_other
    run_lat = job_lat_dir / RUN_ID
    (run_lat / "input_photos_normalized").mkdir(parents=True, exist_ok=True)
    (run_lat / "input_photos_normalized" / normalized_name).write_bytes(jpeg_content)
    manifest_lat = {
        "input_type": "photos",
        "photos": [
            {"image_id": asset_id, "stored_filename": "0001_x.heic", "stored_normalized_filename": normalized_name},
        ],
    }
    (job_lat_dir / "input_manifest.json").write_text(json.dumps(manifest_lat), encoding="utf-8")

    now_upload = datetime(2025, 3, 6, 11, 0, 0, tzinfo=timezone.utc)
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="IMG.heic",
        storage_path=storage_path,
        mime_type="image/heic",
        uploaded_at=now_upload,
    )
    stub_assets = StubListAisleAssetsUseCase([asset])

    try:
        _register_aisle_and_resolver(inv_id, aisle_id, operational_job_id=job_other)
        app.dependency_overrides[get_list_aisle_assets_use_case] = lambda: stub_assets
        with _patch_local_asset_settings(output_dir):
            client = TestClient(app)
            resp = client.get(
                f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/{asset_id}/file",
                params={"job_id": job_bad},
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_list_aisle_assets_use_case, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_result_context_resolver, None)
